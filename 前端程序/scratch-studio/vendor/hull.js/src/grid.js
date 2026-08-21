'use strict';

function Grid (points, cellSize) {
    this.cells = [];
    this.cellSize = cellSize;
    points.forEach(function (point) {
        var cell = this.pointToCell(point);
        this.cells[cell[0]] = this.cells[cell[0]] || [];
        this.cells[cell[0]][cell[1]] = this.cells[cell[0]][cell[1]] || [];
        this.cells[cell[0]][cell[1]].push(point);
    }, this);
}

Grid.prototype.cellPoints = function (x, y) {
    return this.cells[x] && this.cells[x][y] ? this.cells[x][y] : [];
};

Grid.prototype.rangePoints = function (bbox) {
    var topLeft = this.pointToCell([bbox[0], bbox[1]]);
    var bottomRight = this.pointToCell([bbox[2], bbox[3]]);
    var points = [];
    for (var x = topLeft[0]; x <= bottomRight[0]; x++) {
        for (var y = topLeft[1]; y <= bottomRight[1]; y++) {
            points = points.concat(this.cellPoints(x, y));
        }
    }
    return points;
};

Grid.prototype.removePoint = function (point) {
    var cell = this.pointToCell(point);
    var points = this.cells[cell[0]][cell[1]];
    for (var i = 0; i < points.length; i++) {
        if (points[i][0] === point[0] && points[i][1] === point[1]) {
            points.splice(i, 1);
            break;
        }
    }
};

Grid.prototype.pointToCell = function (point) {
    return [parseInt(point[0] / this.cellSize, 10), parseInt(point[1] / this.cellSize, 10)];
};

Grid.prototype.extendBbox = function (bbox, scale) {
    return [
        bbox[0] - scale * this.cellSize,
        bbox[1] - scale * this.cellSize,
        bbox[2] + scale * this.cellSize,
        bbox[3] + scale * this.cellSize
    ];
};

module.exports = function grid (points, cellSize) {
    return new Grid(points, cellSize);
};
