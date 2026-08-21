'use strict';

function cross (origin, a, b) {
    return (a[0] - origin[0]) * (b[1] - origin[1]) -
        (a[1] - origin[1]) * (b[0] - origin[0]);
}

function tangent (pointset) {
    var result = [];
    for (var i = 0; i < pointset.length; i++) {
        while (result.length >= 2 && cross(result[result.length - 2], result[result.length - 1], pointset[i]) <= 0) {
            result.pop();
        }
        result.push(pointset[i]);
    }
    result.pop();
    return result;
}

module.exports = function convex (pointset) {
    var upper = tangent(pointset);
    var lower = tangent(pointset.slice().reverse());
    var result = lower.concat(upper);
    result.push(pointset[0]);
    return result;
};
