'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const hull = require('hull.js');
const immutablePackage = require('immutable/package.json');

const points = [[0, 0], [0, 10], [10, 10], [10, 0], [5, 5]];
assert.ok(hull(points, Infinity).length >= 4, 'patched hull must retain its geometry API');

assert.throws(
    () => hull(points, Infinity, ['.x;global.__hullInjected=true', '.y']),
    /simple property accessor/
);
assert.equal(global.__hullInjected, undefined, 'format strings must never execute code');
assert.equal(immutablePackage.version, '4.3.9');

const distDir = path.resolve(__dirname, '..', 'dist');
if (fs.existsSync(distDir)) {
    for (const filename of fs.readdirSync(distDir)) {
        if (!filename.endsWith('.js') && !filename.endsWith('.map')) continue;
        const source = fs.readFileSync(path.join(distDir, filename), 'utf8');
        assert.doesNotMatch(
            source,
            /new Function\(["']pt["']/,
            `unsafe hull.js formatter remains in ${filename}`
        );
    }
}

console.log('Scratch runtime security overrides verified.');
