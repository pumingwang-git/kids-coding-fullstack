'use strict';

function ccw (x1, y1, x2, y2, x3, y3) {
    var value = ((y3 - y1) * (x2 - x1)) - ((y2 - y1) * (x3 - x1));
    return value >= 0;
}

module.exports = function intersect (first, second) {
    var x1 = first[0][0];
    var y1 = first[0][1];
    var x2 = first[1][0];
    var y2 = first[1][1];
    var x3 = second[0][0];
    var y3 = second[0][1];
    var x4 = second[1][0];
    var y4 = second[1][1];
    return ccw(x1, y1, x3, y3, x4, y4) !== ccw(x2, y2, x3, y3, x4, y4) &&
        ccw(x1, y1, x2, y2, x3, y3) !== ccw(x1, y1, x2, y2, x4, y4);
};
