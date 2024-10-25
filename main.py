"""
devices ::= (device\n)+
device ::= "device" "int" "osd.{INT}" [class STR] 

buckets ::= (bucket)+
bucket ::= [bucket-type](STR) [bucket-name](STR) "{"
    "id" [a unique negative numeric ID] "-" INT
    "weight" [the relative capacity/capability of the item(s)] INT
    "alg" [the bucket type: uniform | list | tree | straw2 ]  
    "hash" [the hash type: 0 by default] 
    "item" [item-name] STR weight [weight] INT
"}"

rules ::= (rules)*
rule ::= "rule" <rulename> {
    id <unique number>
    type [replicated | erasure]
    min_size <min-size>
    max_size <max-size>
    step take <bucket-type> [class <class-name>]
    step [choose|chooseleaf] [firstn|indep] <N> <bucket-type>
    step emit
}
"""

import platform
from pprint import pprint
import sys

assert platform.system() == "Linux", "Systems other than GNU/Linux are NOT supported"

from dataclasses import dataclass
from enum import Enum, auto
from typing import Generator, Literal, NoReturn

BucketT = (
    Literal["osd"]
    | Literal["host"]
    | Literal["chassis"]
    | Literal["rack"]
    | Literal["row"]
    | Literal["pdu"]
    | Literal["pod"]
    | Literal["room"]
    | Literal["datacenter"]
    | Literal["region"]
    | Literal["root"]
)


@dataclass()
class Device:
    seq_num: int
    name: str  # osd.{NUM}
    device_class: str | None = None


class AlgType(Enum):
    uniform = auto()
    list = auto()
    tree = auto()
    straw2 = auto()


@dataclass
class BucketChild:
    name: str
    weight: float


@dataclass
class Bucket:
    name: str
    btype: str
    # weight: float  # don't know how to handle weight for a bucket
    id: int
    children: list[BucketChild]
    alg: AlgType
    # hash: int = 0 # will NOT have hash field


@dataclass
class TakeStep:
    bucket_type: str
    device_class: str | None = None


@dataclass
class ChoiceStep:
    is_chooseleaf: bool
    bucket_type: str


@dataclass
class Rule:
    name: str
    id: int

    min_size: int
    max_size: int

    take: TakeStep
    choose: ChoiceStep


class ReadWordErr(Enum):
    EOF = auto()
    NotIdent = auto()


# actually the worst THING I HAVE EVER WRITTEN
# lexer is for the WEAK
class Tokenizer:
    def __init__(self, text: str):
        self.text = text
        self.cursor = 0

        self.last_newline_pos = -1
        self.row = 1
        self.col = 1

    def parse(self) -> tuple[list[Device], list[Bucket], list[Rule]]:
        return (
            list(self.parse_devices()),
            list(self.parse_buckets()),
            list(self.parse_rules()),
        )

    def skip_n(self, n: int) -> None:
        self.advance(n)

    def read_num(self) -> str | None:
        new = self.cursor
        while new < len(self.text) and self.text[new].isnumeric():
            new += 1

        if new == self.cursor:
            return None

        if new >= len(self.text) or self.text[new].isspace():
            return self.text[self.cursor : new]
        return None

    def read_float(self) -> str | None:
        new = self.cursor
        while new < len(self.text) and self.text[new].isnumeric():
            new += 1
        nonempty_prefix = new != self.cursor

        if new < len(self.text) and self.text[new] == ".":
            new += 1

        suf_start = new
        while new < len(self.text) and self.text[new].isnumeric():
            new += 1
        nonempty_suffix = suf_start != new

        if (nonempty_prefix or nonempty_suffix) and (
            new >= len(self.text) or self.text[new].isspace()
        ):
            return self.text[self.cursor : new]
        return None

    def match_substr(self, target: str) -> bool:
        if self.cursor >= len(self.text):
            return False
        return self.text[self.cursor : self.cursor + len(target)] == target

    def read_word(self) -> str | None:
        new = self.cursor
        if new >= len(self.text) or not self.text[new].isalpha():
            return None
        new += 1
        while new < len(self.text) and (
            self.text[new].isalnum() or self.text[new] in "-_."
        ):
            new += 1
        return self.text[self.cursor : new]

    def report_error(self, msg: str) -> NoReturn:
        if self.cursor < len(self.text):
            right_newline = self.cursor + self.text[self.cursor :].find("\n")
        else:
            right_newline = len(self.text)

        col_prefix = f"{self.row} | "
        print(
            """\
{}{}
{}^
{}{}
""".format(
                col_prefix,
                self.text[self.last_newline_pos + 1 : right_newline],
                " " * (len(col_prefix) + self.col - 1),
                " " * len(col_prefix),
                msg,
            ),
            file=sys.stderr,
        )
        exit(1)

    def bucket_type(self) -> BucketT | None:
        default_types: list[BucketT] = [
            "osd",
            "host",
            "chassis",
            "rack",
            "row",
            "pdu",
            "pod",
            "room",
            "datacenter",
            "region",
            "root",
        ]
        for t in default_types:
            if self.match_substr(t):
                return t
        return None

    def advance(self, n: int = 1):
        self.cursor += n
        self.col += n

    def skip_whitespace_lns(self):
        while self.cursor < len(self.text) and self.text[self.cursor].isspace():
            if self.text[self.cursor] == "\n":
                self.last_newline_pos = self.cursor
                self.row += 1
                self.col = 0
            self.advance()

    def skip_whitespace_lns_required(self) -> None:
        found = False
        while self.cursor < len(self.text) and self.text[self.cursor].isspace():
            if self.text[self.cursor] == "\n":
                found = True
                self.last_newline_pos = self.cursor
                self.row += 1
                self.col = 0
            self.advance()
        if not found:
            self.report_error("new line chars not found")

    def skip_whitespace_to_token_this_line(self) -> None:
        new = self.cursor
        while new < len(self.text) and self.text[new] in (" ", "\t"):
            new += 1
        if (
            new == self.cursor
            and not self.text[self.cursor].isspace()
            and self.text[self.cursor] not in "{}"
        ):
            self.report_error("expected blank space")
        self.advance(new - self.cursor)

    def parse_devices(self) -> Generator[Device, None, None]:
        self.skip_whitespace_lns()
        while True:
            if not self.match_substr("device"):
                maybe_type = self.bucket_type()
                if maybe_type is not None:
                    return
                self.report_error("""expected "device" or buckets description""")

            self.skip_n(len("device"))
            self.skip_whitespace_to_token_this_line()

            device_num = self.read_num()
            if device_num is None:
                self.report_error("expected device number")

            self.skip_n(len(device_num))
            self.skip_whitespace_to_token_this_line()

            if not self.match_substr("osd."):
                self.report_error("expected osd id declaration")

            self.skip_n(len("osd."))
            osd_id = self.read_num()
            if osd_id is None:
                self.report_error("bad osd declaration: expected a number")

            self.skip_n(len(osd_id))
            self.skip_whitespace_to_token_this_line()

            if not self.match_substr("class"):
                yield Device(int(device_num), "osd." + osd_id)
                continue

            self.skip_n(len("class"))
            self.skip_whitespace_to_token_this_line()
            class_name = self.read_word()
            if class_name is None:
                self.report_error("expected device class")
            self.skip_n(len(class_name))
            yield Device(int(device_num), "osd." + osd_id, class_name)
            self.skip_whitespace_lns_required()

    def parse_buckets(self) -> Generator[Bucket, None, None]:
        self.skip_whitespace_lns()
        while True:
            bucket_type = self.bucket_type()
            if bucket_type is None:
                if self.match_substr("rule"):
                    return
                self.report_error("expected bucket type")

            self.skip_n(len(bucket_type))
            self.skip_whitespace_to_token_this_line()

            bucket_name = self.read_word()
            if bucket_name is None:
                self.report_error("expected bucket name")
            self.skip_n(len(bucket_name))
            self.skip_whitespace_to_token_this_line()

            yield self.parse_bucket_block(bucket_name, bucket_type)
            self.skip_whitespace_lns_required()

    def parse_bucket_block(self, bname: str, btype: str) -> Bucket:
        if not self.match_substr("{"):
            self.report_error("expected bucket block start")
        self.skip_n(1)
        self.skip_whitespace_lns_required()

        b_id: int | None = None
        b_alg: AlgType | None = None

        while True:
            field = self.read_word()
            if field is None:
                if self.match_substr("}"):
                    self.report_error("found bucket with no children")
                self.report_error("expected bucket field")
            if field == "id":
                if b_id is not None:
                    self.report_error("found double declaration of a field")

                self.skip_n(len(field))
                self.skip_whitespace_to_token_this_line()

                if not self.match_substr("-"):
                    self.report_error("expected bucket ID (which are always negative)")
                self.skip_n(1)

                bucket_id = self.read_num()
                if bucket_id is None:
                    self.report_error("expected bucket ID (which are always negative)")
                self.skip_n(len(bucket_id))

                b_id = -int(bucket_id)
            elif field == "alg":
                if b_alg is not None:
                    self.report_error("found double declaration of a field")

                self.skip_n(len(field))
                self.skip_whitespace_to_token_this_line()

                alg = self.read_word()
                if alg is None:
                    self.report_error(
                        "expected bucket algorith (one of [uniform | list | tree | straw2])"
                    )
                self.skip_n(len(alg))

                if alg == "uniform":
                    b_alg = AlgType.uniform
                elif alg == "list":
                    b_alg = AlgType.list
                elif alg == "tree":
                    b_alg = AlgType.tree
                elif alg == "straw2":
                    b_alg = AlgType.straw2
                else:
                    self.report_error(
                        "unknown alg type: only uniform, list, tree, straw2 are allowed"
                    )
            elif field == "item":
                children = self.parse_bucket_items()
                if b_id is None:
                    self.report_error("expected bucket to have an ID")
                if not self.match_substr("}"):
                    self.report_error("expected bucket block end")
                self.skip_n(1)
                if b_alg is None:
                    b_alg = AlgType.straw2
                return Bucket(bname, btype, b_id, children, b_alg)
            else:
                self.report_error("unknown field")
            self.skip_whitespace_lns_required()

    def parse_bucket_items(self) -> list[BucketChild]:
        res: list[BucketChild] = []
        while True:
            item = self.parse_bucket_item()
            if item is None:
                break
            res.append(item)
            self.skip_whitespace_lns_required()
        return res

    def parse_bucket_item(self) -> BucketChild | None:
        item_decl = self.read_word()
        if item_decl != "item":
            if self.match_substr("}"):
                return None
            self.report_error("expected item declaration")
        self.skip_n(len(item_decl))
        self.skip_whitespace_to_token_this_line()

        item_name = self.read_word()
        if item_name is None:
            self.report_error("expected item name")
        self.skip_n(len(item_name))
        self.skip_whitespace_to_token_this_line()

        weight: float | None = None
        while True:
            key = self.read_word()
            if key is None:
                if self.cursor >= len(self.text):
                    self.report_error("unexpected EOF")
                if self.text[self.cursor].isspace():  # \n
                    break
                self.report_error("bad field name")

            if key == "weight":
                self.skip_n(len(key))
                self.skip_whitespace_to_token_this_line()

                w = self.read_float()
                if w is None:
                    self.report_error("expected float number")
                weight = float(w)

                self.skip_n(len(w))
                self.skip_whitespace_to_token_this_line()
            else:
                self.report_error("unexpected attribute")

        if weight is None:
            self.report_error("no weight was declared")

        return BucketChild(name=item_name, weight=weight)

    def parse_rules(self) -> Generator[Rule, None, None]:
        self.skip_whitespace_lns()
        while True:
            if self.cursor >= len(self.text):
                return

            if not self.match_substr(target="rule"):
                self.report_error("expected rule declaration")
            self.skip_n(len("rule"))
            self.skip_whitespace_to_token_this_line()

            rule_name = self.read_word()
            if rule_name is None:
                self.report_error("expected rule name")
            self.skip_n(len(rule_name))
            self.skip_whitespace_to_token_this_line()

            yield self.parse_rule_block(rule_name)
            self.skip_whitespace_lns_required()

    def parse_rule_block(self, name: str) -> Rule:
        if not self.match_substr("{"):
            self.report_error("expected rule block")
        self.skip_n(1)
        self.skip_whitespace_lns_required()

        rule_id: int | None = None
        rule_min_size = 1
        rule_max_size = 10
        while True:
            key = self.read_word()
            if key is None:
                self.report_error("expected rule attribute")

            if key == "id":
                self.skip_n(len(key))
                self.skip_whitespace_to_token_this_line()

                found_id = self.read_num()
                if found_id is None:
                    self.report_error("expected rule id")
                rule_id = int(found_id)

                self.skip_n(len(found_id))
                self.skip_whitespace_lns_required()
            elif key == "type":
                self.skip_n(len(key))
                self.skip_whitespace_to_token_this_line()

                rule_type = self.read_word()
                if rule_type is None:
                    self.report_error('expected "replacated" rule type')
                elif rule_type != "replicated":
                    self.report_error('not "replacated" rules are not supported')

                self.skip_n(len(rule_type))
                self.skip_whitespace_lns_required()
            elif key == "min_size":
                self.skip_n(len(key))
                self.skip_whitespace_to_token_this_line()

                found_min_size = self.read_num()
                if found_min_size is None:
                    self.report_error("expected min_size")
                rule_min_size = int(found_min_size)
                self.skip_n(len(found_min_size))
                self.skip_whitespace_lns_required()
            elif key == "max_size":
                self.skip_n(len(key))
                self.skip_whitespace_to_token_this_line()

                found_max_size = self.read_num()
                if found_max_size is None:
                    self.report_error("expected max_size")
                rule_max_size = int(found_max_size)
                self.skip_n(len(found_max_size))
                self.skip_whitespace_lns_required()
            elif key == "step":
                (take, choose) = self.parse_rule_steps()
                if not self.match_substr("}"):
                    self.report_error("expected end of rule declaration")
                self.skip_n(1)

                if rule_id is None:
                    self.report_error("no rule's id was declared")
                return Rule(
                    name=name,
                    id=rule_id,
                    min_size=rule_min_size,
                    max_size=rule_max_size,
                    take=take,
                    choose=choose,
                )
            else:
                self.report_error("unexpected rule field")

    def parse_rule_steps(self) -> tuple[TakeStep, ChoiceStep]:
        t = self.parse_step_take()
        self.skip_whitespace_lns_required()
        c = self.parse_step_choose()
        self.skip_whitespace_lns_required()
        self.parse_step_emit()
        self.skip_whitespace_lns_required()
        return (t, c)

    def parse_step_take(self) -> TakeStep:
        if not self.match_substr("step"):
            self.report_error("expected rule `take` step")
        self.skip_n(len("step"))
        self.skip_whitespace_to_token_this_line()

        if not self.match_substr("take"):
            self.report_error("expected rule `take` step")
        self.skip_n(len("take"))
        self.skip_whitespace_to_token_this_line()

        btype = self.read_word()
        if btype is None:
            self.report_error("expected bucket type")
        self.skip_n(len(btype))
        self.skip_whitespace_to_token_this_line()

        class_opt = self.read_word()
        if class_opt is None:
            self.skip_whitespace_lns_required()
            return TakeStep(btype)

        if class_opt != "class":
            self.report_error(
                "expected to see class option on the same line with `take` step"
            )
        self.skip_n(len(class_opt))
        self.skip_whitespace_to_token_this_line()

        cls = self.read_word()
        if cls is None:
            self.report_error("expected device class")
        self.skip_n(len(cls))

        return TakeStep(btype, cls)

    def parse_step_choose(self) -> ChoiceStep:
        if not self.match_substr("step"):
            self.report_error("expected rule `choose` step")
        self.skip_n(len("step"))
        self.skip_whitespace_to_token_this_line()

        choice = self.read_word()
        if choice not in ("choose", "chooseleaf"):
            self.report_error("expected `choose` or `chooseleaf`")
        self.skip_n(len(choice))
        self.skip_whitespace_to_token_this_line()

        choice_opt = self.read_word()
        if choice_opt != "firstn":
            self.report_error("only `firstn` option is supported")
        self.skip_n(len(choice_opt))
        self.skip_whitespace_to_token_this_line()

        N = self.read_num()
        if N is None:
            self.report_error("expected a number")
        self.skip_n(len(N))
        self.skip_whitespace_to_token_this_line()

        if not self.match_substr("type"):
            self.report_error("expected `type` keyword")
        self.skip_n(len("type"))
        self.skip_whitespace_to_token_this_line()

        bucket_type = self.read_word()
        if bucket_type is None:
            self.report_error("expected bucket type")
        self.skip_n(len(bucket_type))

        return ChoiceStep(is_chooseleaf=choice != "choose", bucket_type=bucket_type)

    def parse_step_emit(self) -> None:
        if not self.match_substr("step"):
            self.report_error("expected rule `take` step")
        self.skip_n(len("step"))
        self.skip_whitespace_to_token_this_line()

        if not self.match_substr("emit"):
            self.report_error("expected `emit`")
        self.skip_n(len("emit"))


text = """\
device 0 osd.0 class hdd
device 1 osd.1 class hdd
device 2 osd.2 class ssd
device 3 osd.3 class ssd
device 4 osd.4 class hdd
device 5 osd.5 class hdd
device 6 osd.6 class ssd
device 7 osd.7 class ssd

host ceph-osd-server-1 {
    id -1
    alg straw2
    item osd.0 weight 1.00
    item osd.1 weight 1.00
    item osd.2 weight 1.00
    item osd.3 weight 1.00
}
host ceph-osd-server-2 {
    id -2
    alg straw2
    item osd.4 weight 1.00
    item osd.5 weight 1.00
item osd.6 weight 1.00
    item osd.7 weight 1.00
}

root default{
id -3
    alg straw2
    item ceph-osd-server-1 weight 4.00
    item ceph-osd-server-2 weight 4.00
}
rule cold {
    id 0
    type replicated
    min_size 2
    max_size 11
    step take default class hdd
    step chooseleaf firstn 0 type host
    step emit
}
rule hot {
    id 1
    type replicated
    min_size 2
    max_size 11
    step take default class ssd
    step chooseleaf firstn 0 type host
    step emit
}
"""


def main():
    t = Tokenizer(text)
    res = t.parse()
    pprint(res)


if __name__ == "__main__":
    main()
