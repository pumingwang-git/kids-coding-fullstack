'use strict';

var intersect = require('./intersect');
var makeGrid = require('./grid');
var formatUtil = require('./format');
var convexHull = require('./convex');
var MAX_CONCAVE_ANGLE_COS = Math.cos(90 / (180 / Math.PI));
var MAX_SEARCH_BBOX_SIZE_PERCENT = 0.6;

function squaredLength (a, b) {
    return Math.pow(b[0] - a[0], 2) + Math.pow(b[1] - a[1], 2);
}

function cosine (origin, a, b) {
    var shiftedA = [a[0] - origin[0], a[1] - origin[1]];
    var shiftedB = [b[0] - origin[0], b[1] - origin[1]];
    var dot = shiftedA[0] * shiftedB[0] + shiftedA[1] * shiftedB[1];
    return dot / Math.sqrt(squaredLength(origin, a) * squaredLength(origin, b));
}

function intersects (segment, pointset) {
    for (var i = 0; i < pointset.length - 1; i++) {
        var existing = [pointset[i], pointset[i + 1]];
        if ((segment[0][0] === existing[0][0] && segment[0][1] === existing[0][1]) ||
            (segment[0][0] === existing[1][0] && segment[0][1] === existing[1][1])) continue;
        if (intersect(segment, existing)) return true;
    }
    return false;
}

function occupiedArea (points) {
    var minX = Infinity;
    var minY = Infinity;
    var maxX = -Infinity;
    var maxY = -Infinity;
    points.forEach(function (point) {
        minX = Math.min(minX, point[0]);
        minY = Math.min(minY, point[1]);
        maxX = Math.max(maxX, point[0]);
        maxY = Math.max(maxY, point[1]);
    });
    return [maxX - minX, maxY - minY];
}

function bboxAround (edge) {
    return [
        Math.min(edge[0][0], edge[1][0]), Math.min(edge[0][1], edge[1][1]),
        Math.max(edge[0][0], edge[1][0]), Math.max(edge[0][1], edge[1][1])
    ];
}

function midpoint (edge, innerPoints, convex) {
    var point = null;
    var angle1 = MAX_CONCAVE_ANGLE_COS;
    var angle2 = MAX_CONCAVE_ANGLE_COS;
    innerPoints.forEach(function (candidate) {
        var candidate1 = cosine(edge[0], edge[1], candidate);
        var candidate2 = cosine(edge[1], edge[0], candidate);
        if (candidate1 > angle1 && candidate2 > angle2 &&
            !intersects([edge[0], candidate], convex) && !intersects([edge[1], candidate], convex)) {
            angle1 = candidate1;
            angle2 = candidate2;
            point = candidate;
        }
    });
    return point;
}

function concave (convex, maxSquaredEdge, maxSearchArea, grid, skippedEdges) {
    var inserted = false;
    for (var i = 0; i < convex.length - 1; i++) {
        var edge = [convex[i], convex[i + 1]];
        var key = edge[0].join() + ',' + edge[1].join();
        if (squaredLength(edge[0], edge[1]) < maxSquaredEdge || skippedEdges[key]) continue;
        var scale = 0;
        var bbox = bboxAround(edge);
        var width;
        var height;
        var point;
        do {
            bbox = grid.extendBbox(bbox, scale++);
            width = bbox[2] - bbox[0];
            height = bbox[3] - bbox[1];
            point = midpoint(edge, grid.rangePoints(bbox), convex);
        } while (point === null && (maxSearchArea[0] > width || maxSearchArea[1] > height));
        if (width >= maxSearchArea[0] && height >= maxSearchArea[1]) skippedEdges[key] = true;
        if (point !== null) {
            convex.splice(i + 1, 0, point);
            grid.removePoint(point);
            inserted = true;
        }
    }
    return inserted ? concave(convex, maxSquaredEdge, maxSearchArea, grid, skippedEdges) : convex;
}

module.exports = function hull (pointset, concavityValue, format) {
    if (pointset.length < 4) return pointset.slice();
    var points = formatUtil.toXy(pointset, format).sort(function (a, b) {
        return a[0] === b[0] ? a[1] - b[1] : a[0] - b[0];
    }).filter(function (point, index, all) {
        return index === 0 || point[0] !== all[index - 1][0] || point[1] !== all[index - 1][1];
    });
    var area = occupiedArea(points);
    var convex = convexHull(points);
    var inner = points.filter(function (point) { return convex.indexOf(point) < 0; });
    var cellSize = Math.ceil(1 / (points.length / (area[0] * area[1])));
    var result = concave(
        convex,
        Math.pow(concavityValue || 20, 2),
        [area[0] * MAX_SEARCH_BBOX_SIZE_PERCENT, area[1] * MAX_SEARCH_BBOX_SIZE_PERCENT],
        makeGrid(inner, cellSize),
        {}
    );
    return formatUtil.fromXy(result, format);
};
