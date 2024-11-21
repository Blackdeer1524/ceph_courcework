import { Canvas, Point, Rect } from 'fabric';

const STATE_IDLE = 'idle';
const STATE_PANNING = 'panning';
// https://stackoverflow.com/a/46862028
Canvas.prototype.toggleDragMode = function (dragMode) {
    // Remember the previous X and Y coordinates for delta calculations
    let lastClientX;
    let lastClientY;
    // Keep track of the state
    let state = STATE_IDLE;
    // We're entering dragmode
    if (dragMode) {
        // Discard any active object
        this.discardActiveObject();
        // Set the cursor to 'move'
        this.defaultCursor = 'move';
        // Loop over all objects and disable events / selectable. We remember its value in a temp variable stored on each object
        this.forEachObject(function (object) {
            object.prevEvented = object.evented;
            object.prevSelectable = object.selectable;
            object.evented = false;
            object.selectable = false;
        });
        // Remove selection ability on the canvas
        this.selection = false;
        // When MouseUp fires, we set the state to idle
        this.on('mouse:up', function (e) {
            state = STATE_IDLE;
        });
        // When MouseDown fires, we set the state to panning
        this.on('mouse:down', (e) => {
            state = STATE_PANNING;
            lastClientX = e.e.clientX;
            lastClientY = e.e.clientY;
        });
        // When the mouse moves, and we're panning (mouse down), we continue
        this.on('mouse:move', (e) => {
            if (state === STATE_PANNING && e && e.e) {
                // let delta = new fabric.Point(e.e.movementX, e.e.movementY); // No Safari support for movementX and movementY
                // For cross-browser compatibility, I had to manually keep track of the delta

                // Calculate deltas
                let deltaX = 0;
                let deltaY = 0;
                if (lastClientX) {
                    deltaX = e.e.clientX - lastClientX;
                }
                if (lastClientY) {
                    deltaY = e.e.clientY - lastClientY;
                }
                // Update the last X and Y values
                lastClientX = e.e.clientX;
                lastClientY = e.e.clientY;

                let delta = new Point(deltaX, deltaY);
                this.relativePan(delta);
            }
        });
    } else {
        // When we exit dragmode, we restore the previous values on all objects
        this.forEachObject(function (object) {
            object.evented = (object.prevEvented !== undefined) ? object.prevEvented : object.evented;
            object.selectable = (object.prevSelectable !== undefined) ? object.prevSelectable : object.selectable;
        });
        // Reset the cursor
        this.defaultCursor = 'default';
        // Remove the event listeners
        this.off('mouse:up');
        this.off('mouse:down');
        this.off('mouse:move');
        // Restore selection ability on the canvas
        this.selection = true;
    }
};
// END

export const mapCanvas = new Canvas("myCanvas")
mapCanvas.backgroundColor = '#ffff00';
mapCanvas.toggleDragMode(true)

// document.getElementById('dragmode').onchange = (e) => {
//     mapCanvas.toggleDragMode(e.currentTarget.checked);
// }

const canvasParent = document.getElementById('myCanvas').parentNode.parentElement;

window.addEventListener('resize', resizeCanvas);
function resizeCanvas() {
    // Set the canvas width and height to match its CSS size
    mapCanvas.setHeight(canvasParent.clientHeight)
    mapCanvas.setWidth(canvasParent.clientWidth)
    mapCanvas.renderAll()
}
resizeCanvas();


canvasParent.addEventListener("wheel", (e) => {
    const currentZoomLevel = mapCanvas.getZoom()
    if (e.deltaY > 0) {
        mapCanvas.setZoom(currentZoomLevel / 1.2)
    } else {
        mapCanvas.setZoom(currentZoomLevel * 1.2)
    }
})

