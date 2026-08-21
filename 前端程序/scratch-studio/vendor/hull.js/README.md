# hull.js security compatibility fork

This package preserves the `hull.js@0.2.10` API and algorithm required by
Scratch Render. Its format adapter replaces the upstream dynamic `Function`
construction with validated property access, closing GHSA-q849-wxrc-vqrp.

The `-wpm.1` suffix identifies this as a local, BSD-licensed maintenance fork;
it is not an upstream hull.js release. Keep the root npm override and run
`npm run test:security` whenever Scratch GUI is upgraded.
