'use strict';

function propertyName (format) {
    if (typeof format !== 'string' || !/^\.[A-Za-z_$][A-Za-z0-9_$]*$/.test(format)) {
        throw new TypeError('hull.js format must be a simple property accessor such as .x');
    }
    return format.slice(1);
}

module.exports = {
    toXy: function (pointset, format) {
        if (format === undefined) return pointset.slice();
        var x = propertyName(format[0]);
        var y = propertyName(format[1]);
        return pointset.map(function (point) {
            return [point[x], point[y]];
        });
    },

    fromXy: function (pointset, format) {
        if (format === undefined) return pointset.slice();
        var x = propertyName(format[0]);
        var y = propertyName(format[1]);
        return pointset.map(function (point) {
            var result = {};
            result[x] = point[0];
            result[y] = point[1];
            return result;
        });
    }
};
