var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __typeError = (msg) => {
  throw TypeError(msg);
};
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __commonJS = (cb, mod) => function __require() {
  return mod || (0, cb[__getOwnPropNames(cb)[0]])((mod = { exports: {} }).exports, mod), mod.exports;
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));
var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);
var __accessCheck = (obj, member, msg) => member.has(obj) || __typeError("Cannot " + msg);
var __privateGet = (obj, member, getter) => (__accessCheck(obj, member, "read from private field"), getter ? getter.call(obj) : member.get(obj));
var __privateAdd = (obj, member, value) => member.has(obj) ? __typeError("Cannot add the same private member more than once") : member instanceof WeakSet ? member.add(obj) : member.set(obj, value);
var __privateSet = (obj, member, value, setter) => (__accessCheck(obj, member, "write to private field"), setter ? setter.call(obj, value) : member.set(obj, value), value);
var __privateMethod = (obj, member, method) => (__accessCheck(obj, member, "access private method"), method);
var __privateWrapper = (obj, member, setter, getter) => ({
  set _(value) {
    __privateSet(obj, member, value, setter);
  },
  get _() {
    return __privateGet(obj, member, getter);
  }
});

// node_modules/lodash/isObject.js
var require_isObject = __commonJS({
  "node_modules/lodash/isObject.js"(exports, module) {
    function isObject(value) {
      var type = typeof value;
      return value != null && (type == "object" || type == "function");
    }
    module.exports = isObject;
  }
});

// node_modules/lodash/_freeGlobal.js
var require_freeGlobal = __commonJS({
  "node_modules/lodash/_freeGlobal.js"(exports, module) {
    var freeGlobal = typeof global == "object" && global && global.Object === Object && global;
    module.exports = freeGlobal;
  }
});

// node_modules/lodash/_root.js
var require_root = __commonJS({
  "node_modules/lodash/_root.js"(exports, module) {
    var freeGlobal = require_freeGlobal();
    var freeSelf = typeof self == "object" && self && self.Object === Object && self;
    var root = freeGlobal || freeSelf || Function("return this")();
    module.exports = root;
  }
});

// node_modules/lodash/now.js
var require_now = __commonJS({
  "node_modules/lodash/now.js"(exports, module) {
    var root = require_root();
    var now = function() {
      return root.Date.now();
    };
    module.exports = now;
  }
});

// node_modules/lodash/_trimmedEndIndex.js
var require_trimmedEndIndex = __commonJS({
  "node_modules/lodash/_trimmedEndIndex.js"(exports, module) {
    var reWhitespace = /\s/;
    function trimmedEndIndex(string) {
      var index = string.length;
      while (index-- && reWhitespace.test(string.charAt(index))) {
      }
      return index;
    }
    module.exports = trimmedEndIndex;
  }
});

// node_modules/lodash/_baseTrim.js
var require_baseTrim = __commonJS({
  "node_modules/lodash/_baseTrim.js"(exports, module) {
    var trimmedEndIndex = require_trimmedEndIndex();
    var reTrimStart = /^\s+/;
    function baseTrim(string) {
      return string ? string.slice(0, trimmedEndIndex(string) + 1).replace(reTrimStart, "") : string;
    }
    module.exports = baseTrim;
  }
});

// node_modules/lodash/_Symbol.js
var require_Symbol = __commonJS({
  "node_modules/lodash/_Symbol.js"(exports, module) {
    var root = require_root();
    var Symbol2 = root.Symbol;
    module.exports = Symbol2;
  }
});

// node_modules/lodash/_getRawTag.js
var require_getRawTag = __commonJS({
  "node_modules/lodash/_getRawTag.js"(exports, module) {
    var Symbol2 = require_Symbol();
    var objectProto = Object.prototype;
    var hasOwnProperty = objectProto.hasOwnProperty;
    var nativeObjectToString = objectProto.toString;
    var symToStringTag = Symbol2 ? Symbol2.toStringTag : void 0;
    function getRawTag(value) {
      var isOwn = hasOwnProperty.call(value, symToStringTag), tag = value[symToStringTag];
      try {
        value[symToStringTag] = void 0;
        var unmasked = true;
      } catch (e4) {
      }
      var result = nativeObjectToString.call(value);
      if (unmasked) {
        if (isOwn) {
          value[symToStringTag] = tag;
        } else {
          delete value[symToStringTag];
        }
      }
      return result;
    }
    module.exports = getRawTag;
  }
});

// node_modules/lodash/_objectToString.js
var require_objectToString = __commonJS({
  "node_modules/lodash/_objectToString.js"(exports, module) {
    var objectProto = Object.prototype;
    var nativeObjectToString = objectProto.toString;
    function objectToString2(value) {
      return nativeObjectToString.call(value);
    }
    module.exports = objectToString2;
  }
});

// node_modules/lodash/_baseGetTag.js
var require_baseGetTag = __commonJS({
  "node_modules/lodash/_baseGetTag.js"(exports, module) {
    var Symbol2 = require_Symbol();
    var getRawTag = require_getRawTag();
    var objectToString2 = require_objectToString();
    var nullTag = "[object Null]";
    var undefinedTag = "[object Undefined]";
    var symToStringTag = Symbol2 ? Symbol2.toStringTag : void 0;
    function baseGetTag(value) {
      if (value == null) {
        return value === void 0 ? undefinedTag : nullTag;
      }
      return symToStringTag && symToStringTag in Object(value) ? getRawTag(value) : objectToString2(value);
    }
    module.exports = baseGetTag;
  }
});

// node_modules/lodash/isObjectLike.js
var require_isObjectLike = __commonJS({
  "node_modules/lodash/isObjectLike.js"(exports, module) {
    function isObjectLike(value) {
      return value != null && typeof value == "object";
    }
    module.exports = isObjectLike;
  }
});

// node_modules/lodash/isSymbol.js
var require_isSymbol = __commonJS({
  "node_modules/lodash/isSymbol.js"(exports, module) {
    var baseGetTag = require_baseGetTag();
    var isObjectLike = require_isObjectLike();
    var symbolTag = "[object Symbol]";
    function isSymbol(value) {
      return typeof value == "symbol" || isObjectLike(value) && baseGetTag(value) == symbolTag;
    }
    module.exports = isSymbol;
  }
});

// node_modules/lodash/toNumber.js
var require_toNumber = __commonJS({
  "node_modules/lodash/toNumber.js"(exports, module) {
    var baseTrim = require_baseTrim();
    var isObject = require_isObject();
    var isSymbol = require_isSymbol();
    var NAN = 0 / 0;
    var reIsBadHex = /^[-+]0x[0-9a-f]+$/i;
    var reIsBinary = /^0b[01]+$/i;
    var reIsOctal = /^0o[0-7]+$/i;
    var freeParseInt = parseInt;
    function toNumber(value) {
      if (typeof value == "number") {
        return value;
      }
      if (isSymbol(value)) {
        return NAN;
      }
      if (isObject(value)) {
        var other = typeof value.valueOf == "function" ? value.valueOf() : value;
        value = isObject(other) ? other + "" : other;
      }
      if (typeof value != "string") {
        return value === 0 ? value : +value;
      }
      value = baseTrim(value);
      var isBinary = reIsBinary.test(value);
      return isBinary || reIsOctal.test(value) ? freeParseInt(value.slice(2), isBinary ? 2 : 8) : reIsBadHex.test(value) ? NAN : +value;
    }
    module.exports = toNumber;
  }
});

// node_modules/lodash/debounce.js
var require_debounce = __commonJS({
  "node_modules/lodash/debounce.js"(exports, module) {
    var isObject = require_isObject();
    var now = require_now();
    var toNumber = require_toNumber();
    var FUNC_ERROR_TEXT = "Expected a function";
    var nativeMax = Math.max;
    var nativeMin = Math.min;
    function debounce3(func, wait, options) {
      var lastArgs, lastThis, maxWait, result, timerId, lastCallTime, lastInvokeTime = 0, leading = false, maxing = false, trailing = true;
      if (typeof func != "function") {
        throw new TypeError(FUNC_ERROR_TEXT);
      }
      wait = toNumber(wait) || 0;
      if (isObject(options)) {
        leading = !!options.leading;
        maxing = "maxWait" in options;
        maxWait = maxing ? nativeMax(toNumber(options.maxWait) || 0, wait) : maxWait;
        trailing = "trailing" in options ? !!options.trailing : trailing;
      }
      function invokeFunc(time) {
        var args = lastArgs, thisArg = lastThis;
        lastArgs = lastThis = void 0;
        lastInvokeTime = time;
        result = func.apply(thisArg, args);
        return result;
      }
      function leadingEdge(time) {
        lastInvokeTime = time;
        timerId = setTimeout(timerExpired, wait);
        return leading ? invokeFunc(time) : result;
      }
      function remainingWait(time) {
        var timeSinceLastCall = time - lastCallTime, timeSinceLastInvoke = time - lastInvokeTime, timeWaiting = wait - timeSinceLastCall;
        return maxing ? nativeMin(timeWaiting, maxWait - timeSinceLastInvoke) : timeWaiting;
      }
      function shouldInvoke(time) {
        var timeSinceLastCall = time - lastCallTime, timeSinceLastInvoke = time - lastInvokeTime;
        return lastCallTime === void 0 || timeSinceLastCall >= wait || timeSinceLastCall < 0 || maxing && timeSinceLastInvoke >= maxWait;
      }
      function timerExpired() {
        var time = now();
        if (shouldInvoke(time)) {
          return trailingEdge(time);
        }
        timerId = setTimeout(timerExpired, remainingWait(time));
      }
      function trailingEdge(time) {
        timerId = void 0;
        if (trailing && lastArgs) {
          return invokeFunc(time);
        }
        lastArgs = lastThis = void 0;
        return result;
      }
      function cancel() {
        if (timerId !== void 0) {
          clearTimeout(timerId);
        }
        lastInvokeTime = 0;
        lastArgs = lastCallTime = lastThis = timerId = void 0;
      }
      function flush() {
        return timerId === void 0 ? result : trailingEdge(now());
      }
      function debounced() {
        var time = now(), isInvoking = shouldInvoke(time);
        lastArgs = arguments;
        lastThis = this;
        lastCallTime = time;
        if (isInvoking) {
          if (timerId === void 0) {
            return leadingEdge(lastCallTime);
          }
          if (maxing) {
            clearTimeout(timerId);
            timerId = setTimeout(timerExpired, wait);
            return invokeFunc(lastCallTime);
          }
        }
        if (timerId === void 0) {
          timerId = setTimeout(timerExpired, wait);
        }
        return result;
      }
      debounced.cancel = cancel;
      debounced.flush = flush;
      return debounced;
    }
    module.exports = debounce3;
  }
});

// node_modules/lodash/throttle.js
var require_throttle = __commonJS({
  "node_modules/lodash/throttle.js"(exports, module) {
    var debounce3 = require_debounce();
    var isObject = require_isObject();
    var FUNC_ERROR_TEXT = "Expected a function";
    function throttle2(func, wait, options) {
      var leading = true, trailing = true;
      if (typeof func != "function") {
        throw new TypeError(FUNC_ERROR_TEXT);
      }
      if (isObject(options)) {
        leading = "leading" in options ? !!options.leading : leading;
        trailing = "trailing" in options ? !!options.trailing : trailing;
      }
      return debounce3(func, wait, {
        "leading": leading,
        "maxWait": wait,
        "trailing": trailing
      });
    }
    module.exports = throttle2;
  }
});

// node_modules/namespace-emitter/index.js
var require_namespace_emitter = __commonJS({
  "node_modules/namespace-emitter/index.js"(exports, module) {
    module.exports = function createNamespaceEmitter() {
      var emitter = {};
      var _fns = emitter._fns = {};
      emitter.emit = function emit(event, arg1, arg2, arg3, arg4, arg5, arg6) {
        var toEmit = getListeners(event);
        if (toEmit.length) {
          emitAll(event, toEmit, [arg1, arg2, arg3, arg4, arg5, arg6]);
        }
      };
      emitter.on = function on2(event, fn2) {
        if (!_fns[event]) {
          _fns[event] = [];
        }
        _fns[event].push(fn2);
      };
      emitter.once = function once(event, fn2) {
        function one() {
          fn2.apply(this, arguments);
          emitter.off(event, one);
        }
        this.on(event, one);
      };
      emitter.off = function off(event, fn2) {
        var keep = [];
        if (event && fn2) {
          var fns = this._fns[event];
          var i4 = 0;
          var l4 = fns ? fns.length : 0;
          for (i4; i4 < l4; i4++) {
            if (fns[i4] !== fn2) {
              keep.push(fns[i4]);
            }
          }
        }
        keep.length ? this._fns[event] = keep : delete this._fns[event];
      };
      function getListeners(e4) {
        var out = _fns[e4] ? _fns[e4] : [];
        var idx = e4.indexOf(":");
        var args = idx === -1 ? [e4] : [e4.substring(0, idx), e4.substring(idx + 1)];
        var keys = Object.keys(_fns);
        var i4 = 0;
        var l4 = keys.length;
        for (i4; i4 < l4; i4++) {
          var key = keys[i4];
          if (key === "*") {
            out = out.concat(_fns[key]);
          }
          if (args.length === 2 && args[0] === key) {
            out = out.concat(_fns[key]);
            break;
          }
        }
        return out;
      }
      function emitAll(e4, fns, args) {
        var i4 = 0;
        var l4 = fns.length;
        for (i4; i4 < l4; i4++) {
          if (!fns[i4]) break;
          fns[i4].event = e4;
          fns[i4].apply(fns[i4], args);
        }
      }
      return emitter;
    };
  }
});

// node_modules/@transloadit/prettier-bytes/dist/prettierBytes.js
var require_prettierBytes = __commonJS({
  "node_modules/@transloadit/prettier-bytes/dist/prettierBytes.js"(exports, module) {
    "use strict";
    module.exports = function prettierBytes4(input) {
      if (typeof input !== "number" || Number.isNaN(input)) {
        throw new TypeError(`Expected a number, got ${typeof input}`);
      }
      const neg = input < 0;
      let num = Math.abs(input);
      if (neg) {
        num = -num;
      }
      if (num === 0) {
        return "0 B";
      }
      const units = ["B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB"];
      const exponent = Math.min(Math.floor(Math.log(num) / Math.log(1024)), units.length - 1);
      const value = Number(num / 1024 ** exponent);
      const unit = units[exponent];
      return `${value >= 10 || value % 1 === 0 ? Math.round(value) : value.toFixed(1)} ${unit}`;
    };
  }
});

// node_modules/wildcard/index.js
var require_wildcard = __commonJS({
  "node_modules/wildcard/index.js"(exports, module) {
    "use strict";
    function WildcardMatcher(text, separator2) {
      this.text = text = text || "";
      this.hasWild = ~text.indexOf("*");
      this.separator = separator2;
      this.parts = text.split(separator2);
    }
    WildcardMatcher.prototype.match = function(input) {
      var matches = true;
      var parts = this.parts;
      var ii;
      var partsCount = parts.length;
      var testParts;
      if (typeof input == "string" || input instanceof String) {
        if (!this.hasWild && this.text != input) {
          matches = false;
        } else {
          testParts = (input || "").split(this.separator);
          for (ii = 0; matches && ii < partsCount; ii++) {
            if (parts[ii] === "*") {
              continue;
            } else if (ii < testParts.length) {
              matches = parts[ii] === testParts[ii];
            } else {
              matches = false;
            }
          }
          matches = matches && testParts;
        }
      } else if (typeof input.splice == "function") {
        matches = [];
        for (ii = input.length; ii--; ) {
          if (this.match(input[ii])) {
            matches[matches.length] = input[ii];
          }
        }
      } else if (typeof input == "object") {
        matches = {};
        for (var key in input) {
          if (this.match(key)) {
            matches[key] = input[key];
          }
        }
      }
      return matches;
    };
    module.exports = function(text, test, separator2) {
      var matcher = new WildcardMatcher(text, separator2 || /[\/\.]/);
      if (typeof test != "undefined") {
        return matcher.match(test);
      }
      return matcher;
    };
  }
});

// node_modules/mime-match/index.js
var require_mime_match = __commonJS({
  "node_modules/mime-match/index.js"(exports, module) {
    var wildcard = require_wildcard();
    var reMimePartSplit = /[\/\+\.]/;
    module.exports = function(target, pattern) {
      function test(pattern2) {
        var result = wildcard(pattern2, target, reMimePartSplit);
        return result && result.length >= 2;
      }
      return pattern ? test(pattern.split(";")[0]) : test;
    };
  }
});

// node_modules/classnames/index.js
var require_classnames = __commonJS({
  "node_modules/classnames/index.js"(exports, module) {
    (function() {
      "use strict";
      var hasOwn = {}.hasOwnProperty;
      function classNames15() {
        var classes = "";
        for (var i4 = 0; i4 < arguments.length; i4++) {
          var arg = arguments[i4];
          if (arg) {
            classes = appendClass(classes, parseValue(arg));
          }
        }
        return classes;
      }
      function parseValue(arg) {
        if (typeof arg === "string" || typeof arg === "number") {
          return arg;
        }
        if (typeof arg !== "object") {
          return "";
        }
        if (Array.isArray(arg)) {
          return classNames15.apply(null, arg);
        }
        if (arg.toString !== Object.prototype.toString && !arg.toString.toString().includes("[native code]")) {
          return arg.toString();
        }
        var classes = "";
        for (var key in arg) {
          if (hasOwn.call(arg, key) && arg[key]) {
            classes = appendClass(classes, key);
          }
        }
        return classes;
      }
      function appendClass(value, newClass) {
        if (!newClass) {
          return value;
        }
        if (value) {
          return value + " " + newClass;
        }
        return value + newClass;
      }
      if (typeof module !== "undefined" && module.exports) {
        classNames15.default = classNames15;
        module.exports = classNames15;
      } else if (typeof define === "function" && typeof define.amd === "object" && define.amd) {
        define("classnames", [], function() {
          return classNames15;
        });
      } else {
        window.classNames = classNames15;
      }
    })();
  }
});

// node_modules/eventemitter3/index.js
var require_eventemitter3 = __commonJS({
  "node_modules/eventemitter3/index.js"(exports, module) {
    "use strict";
    var has = Object.prototype.hasOwnProperty;
    var prefix = "~";
    function Events() {
    }
    if (Object.create) {
      Events.prototype = /* @__PURE__ */ Object.create(null);
      if (!new Events().__proto__) prefix = false;
    }
    function EE(fn2, context, once) {
      this.fn = fn2;
      this.context = context;
      this.once = once || false;
    }
    function addListener(emitter, event, fn2, context, once) {
      if (typeof fn2 !== "function") {
        throw new TypeError("The listener must be a function");
      }
      var listener = new EE(fn2, context || emitter, once), evt = prefix ? prefix + event : event;
      if (!emitter._events[evt]) emitter._events[evt] = listener, emitter._eventsCount++;
      else if (!emitter._events[evt].fn) emitter._events[evt].push(listener);
      else emitter._events[evt] = [emitter._events[evt], listener];
      return emitter;
    }
    function clearEvent(emitter, evt) {
      if (--emitter._eventsCount === 0) emitter._events = new Events();
      else delete emitter._events[evt];
    }
    function EventEmitter2() {
      this._events = new Events();
      this._eventsCount = 0;
    }
    EventEmitter2.prototype.eventNames = function eventNames() {
      var names = [], events, name;
      if (this._eventsCount === 0) return names;
      for (name in events = this._events) {
        if (has.call(events, name)) names.push(prefix ? name.slice(1) : name);
      }
      if (Object.getOwnPropertySymbols) {
        return names.concat(Object.getOwnPropertySymbols(events));
      }
      return names;
    };
    EventEmitter2.prototype.listeners = function listeners(event) {
      var evt = prefix ? prefix + event : event, handlers = this._events[evt];
      if (!handlers) return [];
      if (handlers.fn) return [handlers.fn];
      for (var i4 = 0, l4 = handlers.length, ee3 = new Array(l4); i4 < l4; i4++) {
        ee3[i4] = handlers[i4].fn;
      }
      return ee3;
    };
    EventEmitter2.prototype.listenerCount = function listenerCount(event) {
      var evt = prefix ? prefix + event : event, listeners = this._events[evt];
      if (!listeners) return 0;
      if (listeners.fn) return 1;
      return listeners.length;
    };
    EventEmitter2.prototype.emit = function emit(event, a1, a22, a32, a4, a5) {
      var evt = prefix ? prefix + event : event;
      if (!this._events[evt]) return false;
      var listeners = this._events[evt], len = arguments.length, args, i4;
      if (listeners.fn) {
        if (listeners.once) this.removeListener(event, listeners.fn, void 0, true);
        switch (len) {
          case 1:
            return listeners.fn.call(listeners.context), true;
          case 2:
            return listeners.fn.call(listeners.context, a1), true;
          case 3:
            return listeners.fn.call(listeners.context, a1, a22), true;
          case 4:
            return listeners.fn.call(listeners.context, a1, a22, a32), true;
          case 5:
            return listeners.fn.call(listeners.context, a1, a22, a32, a4), true;
          case 6:
            return listeners.fn.call(listeners.context, a1, a22, a32, a4, a5), true;
        }
        for (i4 = 1, args = new Array(len - 1); i4 < len; i4++) {
          args[i4 - 1] = arguments[i4];
        }
        listeners.fn.apply(listeners.context, args);
      } else {
        var length = listeners.length, j5;
        for (i4 = 0; i4 < length; i4++) {
          if (listeners[i4].once) this.removeListener(event, listeners[i4].fn, void 0, true);
          switch (len) {
            case 1:
              listeners[i4].fn.call(listeners[i4].context);
              break;
            case 2:
              listeners[i4].fn.call(listeners[i4].context, a1);
              break;
            case 3:
              listeners[i4].fn.call(listeners[i4].context, a1, a22);
              break;
            case 4:
              listeners[i4].fn.call(listeners[i4].context, a1, a22, a32);
              break;
            default:
              if (!args) for (j5 = 1, args = new Array(len - 1); j5 < len; j5++) {
                args[j5 - 1] = arguments[j5];
              }
              listeners[i4].fn.apply(listeners[i4].context, args);
          }
        }
      }
      return true;
    };
    EventEmitter2.prototype.on = function on2(event, fn2, context) {
      return addListener(this, event, fn2, context, false);
    };
    EventEmitter2.prototype.once = function once(event, fn2, context) {
      return addListener(this, event, fn2, context, true);
    };
    EventEmitter2.prototype.removeListener = function removeListener(event, fn2, context, once) {
      var evt = prefix ? prefix + event : event;
      if (!this._events[evt]) return this;
      if (!fn2) {
        clearEvent(this, evt);
        return this;
      }
      var listeners = this._events[evt];
      if (listeners.fn) {
        if (listeners.fn === fn2 && (!once || listeners.once) && (!context || listeners.context === context)) {
          clearEvent(this, evt);
        }
      } else {
        for (var i4 = 0, events = [], length = listeners.length; i4 < length; i4++) {
          if (listeners[i4].fn !== fn2 || once && !listeners[i4].once || context && listeners[i4].context !== context) {
            events.push(listeners[i4]);
          }
        }
        if (events.length) this._events[evt] = events.length === 1 ? events[0] : events;
        else clearEvent(this, evt);
      }
      return this;
    };
    EventEmitter2.prototype.removeAllListeners = function removeAllListeners(event) {
      var evt;
      if (event) {
        evt = prefix ? prefix + event : event;
        if (this._events[evt]) clearEvent(this, evt);
      } else {
        this._events = new Events();
        this._eventsCount = 0;
      }
      return this;
    };
    EventEmitter2.prototype.off = EventEmitter2.prototype.removeListener;
    EventEmitter2.prototype.addListener = EventEmitter2.prototype.on;
    EventEmitter2.prefixed = prefix;
    EventEmitter2.EventEmitter = EventEmitter2;
    if ("undefined" !== typeof module) {
      module.exports = EventEmitter2;
    }
  }
});

// node_modules/retry/lib/retry_operation.js
var require_retry_operation = __commonJS({
  "node_modules/retry/lib/retry_operation.js"(exports, module) {
    function RetryOperation(timeouts, options) {
      if (typeof options === "boolean") {
        options = { forever: options };
      }
      this._originalTimeouts = JSON.parse(JSON.stringify(timeouts));
      this._timeouts = timeouts;
      this._options = options || {};
      this._maxRetryTime = options && options.maxRetryTime || Infinity;
      this._fn = null;
      this._errors = [];
      this._attempts = 1;
      this._operationTimeout = null;
      this._operationTimeoutCb = null;
      this._timeout = null;
      this._operationStart = null;
      this._timer = null;
      if (this._options.forever) {
        this._cachedTimeouts = this._timeouts.slice(0);
      }
    }
    module.exports = RetryOperation;
    RetryOperation.prototype.reset = function() {
      this._attempts = 1;
      this._timeouts = this._originalTimeouts.slice(0);
    };
    RetryOperation.prototype.stop = function() {
      if (this._timeout) {
        clearTimeout(this._timeout);
      }
      if (this._timer) {
        clearTimeout(this._timer);
      }
      this._timeouts = [];
      this._cachedTimeouts = null;
    };
    RetryOperation.prototype.retry = function(err) {
      if (this._timeout) {
        clearTimeout(this._timeout);
      }
      if (!err) {
        return false;
      }
      var currentTime = (/* @__PURE__ */ new Date()).getTime();
      if (err && currentTime - this._operationStart >= this._maxRetryTime) {
        this._errors.push(err);
        this._errors.unshift(new Error("RetryOperation timeout occurred"));
        return false;
      }
      this._errors.push(err);
      var timeout = this._timeouts.shift();
      if (timeout === void 0) {
        if (this._cachedTimeouts) {
          this._errors.splice(0, this._errors.length - 1);
          timeout = this._cachedTimeouts.slice(-1);
        } else {
          return false;
        }
      }
      var self2 = this;
      this._timer = setTimeout(function() {
        self2._attempts++;
        if (self2._operationTimeoutCb) {
          self2._timeout = setTimeout(function() {
            self2._operationTimeoutCb(self2._attempts);
          }, self2._operationTimeout);
          if (self2._options.unref) {
            self2._timeout.unref();
          }
        }
        self2._fn(self2._attempts);
      }, timeout);
      if (this._options.unref) {
        this._timer.unref();
      }
      return true;
    };
    RetryOperation.prototype.attempt = function(fn2, timeoutOps) {
      this._fn = fn2;
      if (timeoutOps) {
        if (timeoutOps.timeout) {
          this._operationTimeout = timeoutOps.timeout;
        }
        if (timeoutOps.cb) {
          this._operationTimeoutCb = timeoutOps.cb;
        }
      }
      var self2 = this;
      if (this._operationTimeoutCb) {
        this._timeout = setTimeout(function() {
          self2._operationTimeoutCb();
        }, self2._operationTimeout);
      }
      this._operationStart = (/* @__PURE__ */ new Date()).getTime();
      this._fn(this._attempts);
    };
    RetryOperation.prototype.try = function(fn2) {
      console.log("Using RetryOperation.try() is deprecated");
      this.attempt(fn2);
    };
    RetryOperation.prototype.start = function(fn2) {
      console.log("Using RetryOperation.start() is deprecated");
      this.attempt(fn2);
    };
    RetryOperation.prototype.start = RetryOperation.prototype.try;
    RetryOperation.prototype.errors = function() {
      return this._errors;
    };
    RetryOperation.prototype.attempts = function() {
      return this._attempts;
    };
    RetryOperation.prototype.mainError = function() {
      if (this._errors.length === 0) {
        return null;
      }
      var counts = {};
      var mainError = null;
      var mainErrorCount = 0;
      for (var i4 = 0; i4 < this._errors.length; i4++) {
        var error = this._errors[i4];
        var message = error.message;
        var count = (counts[message] || 0) + 1;
        counts[message] = count;
        if (count >= mainErrorCount) {
          mainError = error;
          mainErrorCount = count;
        }
      }
      return mainError;
    };
  }
});

// node_modules/retry/lib/retry.js
var require_retry = __commonJS({
  "node_modules/retry/lib/retry.js"(exports) {
    var RetryOperation = require_retry_operation();
    exports.operation = function(options) {
      var timeouts = exports.timeouts(options);
      return new RetryOperation(timeouts, {
        forever: options && (options.forever || options.retries === Infinity),
        unref: options && options.unref,
        maxRetryTime: options && options.maxRetryTime
      });
    };
    exports.timeouts = function(options) {
      if (options instanceof Array) {
        return [].concat(options);
      }
      var opts = {
        retries: 10,
        factor: 2,
        minTimeout: 1 * 1e3,
        maxTimeout: Infinity,
        randomize: false
      };
      for (var key in options) {
        opts[key] = options[key];
      }
      if (opts.minTimeout > opts.maxTimeout) {
        throw new Error("minTimeout is greater than maxTimeout");
      }
      var timeouts = [];
      for (var i4 = 0; i4 < opts.retries; i4++) {
        timeouts.push(this.createTimeout(i4, opts));
      }
      if (options && options.forever && !timeouts.length) {
        timeouts.push(this.createTimeout(i4, opts));
      }
      timeouts.sort(function(a4, b3) {
        return a4 - b3;
      });
      return timeouts;
    };
    exports.createTimeout = function(attempt, opts) {
      var random = opts.randomize ? Math.random() + 1 : 1;
      var timeout = Math.round(random * Math.max(opts.minTimeout, 1) * Math.pow(opts.factor, attempt));
      timeout = Math.min(timeout, opts.maxTimeout);
      return timeout;
    };
    exports.wrap = function(obj, options, methods) {
      if (options instanceof Array) {
        methods = options;
        options = null;
      }
      if (!methods) {
        methods = [];
        for (var key in obj) {
          if (typeof obj[key] === "function") {
            methods.push(key);
          }
        }
      }
      for (var i4 = 0; i4 < methods.length; i4++) {
        var method = methods[i4];
        var original = obj[method];
        obj[method] = function retryWrapper(original2) {
          var op = exports.operation(options);
          var args = Array.prototype.slice.call(arguments, 1);
          var callback = args.pop();
          args.push(function(err) {
            if (op.retry(err)) {
              return;
            }
            if (err) {
              arguments[0] = op.mainError();
            }
            callback.apply(this, arguments);
          });
          op.attempt(function() {
            original2.apply(obj, args);
          });
        }.bind(obj, original);
        obj[method].options = options;
      }
    };
  }
});

// node_modules/retry/index.js
var require_retry2 = __commonJS({
  "node_modules/retry/index.js"(exports, module) {
    module.exports = require_retry();
  }
});

// node_modules/@uppy/utils/lib/Translator.js
function insertReplacement(source, rx, replacement) {
  const newParts = [];
  source.forEach((chunk) => {
    if (typeof chunk !== "string") {
      return newParts.push(chunk);
    }
    return rx[Symbol.split](chunk).forEach((raw, i4, list) => {
      if (raw !== "") {
        newParts.push(raw);
      }
      if (i4 < list.length - 1) {
        newParts.push(replacement);
      }
    });
  });
  return newParts;
}
function interpolate(phrase, options) {
  const dollarRegex = /\$/g;
  const dollarBillsYall = "$$$$";
  let interpolated = [phrase];
  if (options == null)
    return interpolated;
  for (const arg of Object.keys(options)) {
    if (arg !== "_") {
      let replacement = options[arg];
      if (typeof replacement === "string") {
        replacement = dollarRegex[Symbol.replace](replacement, dollarBillsYall);
      }
      interpolated = insertReplacement(interpolated, new RegExp(`%\\{${arg}\\}`, "g"), replacement);
    }
  }
  return interpolated;
}
var defaultOnMissingKey = (key) => {
  throw new Error(`missing string: ${key}`);
};
var _onMissingKey, _Translator_instances, apply_fn;
var Translator = class {
  constructor(locales, { onMissingKey = defaultOnMissingKey } = {}) {
    __privateAdd(this, _Translator_instances);
    __publicField(this, "locale");
    __privateAdd(this, _onMissingKey);
    this.locale = {
      strings: {},
      pluralize(n3) {
        if (n3 === 1) {
          return 0;
        }
        return 1;
      }
    };
    if (Array.isArray(locales)) {
      locales.forEach(__privateMethod(this, _Translator_instances, apply_fn), this);
    } else {
      __privateMethod(this, _Translator_instances, apply_fn).call(this, locales);
    }
    __privateSet(this, _onMissingKey, onMissingKey);
  }
  /**
   * Public translate method
   *
   * @param key
   * @param options with values that will be used later to replace placeholders in string
   * @returns string translated (and interpolated)
   */
  translate(key, options) {
    return this.translateArray(key, options).join("");
  }
  /**
   * Get a translation and return the translated and interpolated parts as an array.
   *
   * @returns The translated and interpolated parts, in order.
   */
  translateArray(key, options) {
    let string = this.locale.strings[key];
    if (string == null) {
      __privateGet(this, _onMissingKey).call(this, key);
      string = key;
    }
    const hasPluralForms = typeof string === "object";
    if (hasPluralForms) {
      if (options && typeof options.smart_count !== "undefined") {
        const plural = this.locale.pluralize(options.smart_count);
        return interpolate(string[plural], options);
      }
      throw new Error("Attempted to use a string with plural forms, but no value was given for %{smart_count}");
    }
    if (typeof string !== "string") {
      throw new Error(`string was not a string`);
    }
    return interpolate(string, options);
  }
};
_onMissingKey = new WeakMap();
_Translator_instances = new WeakSet();
apply_fn = function(locale) {
  if (!locale?.strings) {
    return;
  }
  const prevLocale = this.locale;
  Object.assign(this.locale, {
    strings: { ...prevLocale.strings, ...locale.strings },
    pluralize: locale.pluralize || prevLocale.pluralize
  });
};

// node_modules/@uppy/core/lib/BasePlugin.js
var BasePlugin = class {
  constructor(uppy, opts) {
    __publicField(this, "uppy");
    __publicField(this, "opts");
    __publicField(this, "id");
    __publicField(this, "defaultLocale");
    __publicField(this, "i18n");
    __publicField(this, "i18nArray");
    __publicField(this, "type");
    __publicField(this, "VERSION");
    this.uppy = uppy;
    this.opts = opts ?? {};
  }
  getPluginState() {
    const { plugins } = this.uppy.getState();
    return plugins?.[this.id] || {};
  }
  setPluginState(update) {
    const { plugins } = this.uppy.getState();
    this.uppy.setState({
      plugins: {
        ...plugins,
        [this.id]: {
          ...plugins[this.id],
          ...update
        }
      }
    });
  }
  setOptions(newOpts) {
    this.opts = { ...this.opts, ...newOpts };
    this.setPluginState(void 0);
    this.i18nInit();
  }
  i18nInit() {
    const translator = new Translator([
      this.defaultLocale,
      this.uppy.locale,
      this.opts.locale
    ]);
    this.i18n = translator.translate.bind(translator);
    this.i18nArray = translator.translateArray.bind(translator);
    this.setPluginState(void 0);
  }
  /**
   * Extendable methods
   * ==================
   * These methods are here to serve as an overview of the extendable methods as well as
   * making them not conditional in use, such as `if (this.afterUpdate)`.
   */
  addTarget(plugin) {
    throw new Error("Extend the addTarget method to add your plugin to another plugin's target");
  }
  install() {
  }
  uninstall() {
  }
  update(state) {
  }
  // Called after every state update, after everything's mounted. Debounced.
  afterUpdate() {
  }
};

// node_modules/@uppy/utils/lib/getTimeStamp.js
function pad(number) {
  return number < 10 ? `0${number}` : number.toString();
}
function getTimeStamp() {
  const date = /* @__PURE__ */ new Date();
  const hours = pad(date.getHours());
  const minutes = pad(date.getMinutes());
  const seconds = pad(date.getSeconds());
  return `${hours}:${minutes}:${seconds}`;
}

// node_modules/@uppy/core/lib/loggers.js
var justErrorsLogger = {
  debug: () => {
  },
  warn: () => {
  },
  error: (...args) => console.error(`[Uppy] [${getTimeStamp()}]`, ...args)
};
var debugLogger = {
  debug: (...args) => console.debug(`[Uppy] [${getTimeStamp()}]`, ...args),
  warn: (...args) => console.warn(`[Uppy] [${getTimeStamp()}]`, ...args),
  error: (...args) => console.error(`[Uppy] [${getTimeStamp()}]`, ...args)
};

// node_modules/@uppy/utils/lib/isDOMElement.js
function isDOMElement(obj) {
  if (typeof obj !== "object" || obj === null)
    return false;
  if (!("nodeType" in obj))
    return false;
  return obj.nodeType === Node.ELEMENT_NODE;
}

// node_modules/@uppy/utils/lib/findDOMElement.js
function findDOMElement(element, context = document) {
  if (typeof element === "string") {
    return context.querySelector(element);
  }
  if (isDOMElement(element)) {
    return element;
  }
  return null;
}
var findDOMElement_default = findDOMElement;

// node_modules/@uppy/utils/lib/getTextDirection.js
function getTextDirection(element) {
  while (element && !element.dir) {
    element = element.parentNode;
  }
  return element?.dir;
}
var getTextDirection_default = getTextDirection;

// node_modules/preact/dist/preact.module.js
var n;
var l;
var u;
var t;
var i;
var r;
var o;
var e;
var f;
var c;
var a;
var s;
var h;
var p;
var v;
var y;
var d = {};
var w = [];
var _ = /acit|ex(?:s|g|n|p|$)|rph|grid|ows|mnc|ntw|ine[ch]|zoo|^ord|itera/i;
var g = Array.isArray;
function m(n3, l4) {
  for (var u5 in l4) n3[u5] = l4[u5];
  return n3;
}
function b(n3) {
  n3 && n3.parentNode && n3.parentNode.removeChild(n3);
}
function k(l4, u5, t4) {
  var i4, r4, o4, e4 = {};
  for (o4 in u5) "key" == o4 ? i4 = u5[o4] : "ref" == o4 ? r4 = u5[o4] : e4[o4] = u5[o4];
  if (arguments.length > 2 && (e4.children = arguments.length > 3 ? n.call(arguments, 2) : t4), "function" == typeof l4 && null != l4.defaultProps) for (o4 in l4.defaultProps) void 0 === e4[o4] && (e4[o4] = l4.defaultProps[o4]);
  return x(l4, e4, i4, r4, null);
}
function x(n3, t4, i4, r4, o4) {
  var e4 = { type: n3, props: t4, key: i4, ref: r4, __k: null, __: null, __b: 0, __e: null, __c: null, constructor: void 0, __v: null == o4 ? ++u : o4, __i: -1, __u: 0 };
  return null == o4 && null != l.vnode && l.vnode(e4), e4;
}
function M() {
  return { current: null };
}
function S(n3) {
  return n3.children;
}
function C(n3, l4) {
  this.props = n3, this.context = l4;
}
function $(n3, l4) {
  if (null == l4) return n3.__ ? $(n3.__, n3.__i + 1) : null;
  for (var u5; l4 < n3.__k.length; l4++) if (null != (u5 = n3.__k[l4]) && null != u5.__e) return u5.__e;
  return "function" == typeof n3.type ? $(n3) : null;
}
function I(n3) {
  if (n3.__P && n3.__d) {
    var u5 = n3.__v, t4 = u5.__e, i4 = [], r4 = [], o4 = m({}, u5);
    o4.__v = u5.__v + 1, l.vnode && l.vnode(o4), q(n3.__P, o4, u5, n3.__n, n3.__P.namespaceURI, 32 & u5.__u ? [t4] : null, i4, null == t4 ? $(u5) : t4, !!(32 & u5.__u), r4), o4.__v = u5.__v, o4.__.__k[o4.__i] = o4, D(i4, o4, r4), u5.__e = u5.__ = null, o4.__e != t4 && P(o4);
  }
}
function P(n3) {
  if (null != (n3 = n3.__) && null != n3.__c) return n3.__e = n3.__c.base = null, n3.__k.some(function(l4) {
    if (null != l4 && null != l4.__e) return n3.__e = n3.__c.base = l4.__e;
  }), P(n3);
}
function A(n3) {
  (!n3.__d && (n3.__d = true) && i.push(n3) && !H.__r++ || r != l.debounceRendering) && ((r = l.debounceRendering) || o)(H);
}
function H() {
  try {
    for (var n3, l4 = 1; i.length; ) i.length > l4 && i.sort(e), n3 = i.shift(), l4 = i.length, I(n3);
  } finally {
    i.length = H.__r = 0;
  }
}
function L(n3, l4, u5, t4, i4, r4, o4, e4, f5, c4, a4) {
  var s4, h4, p4, v4, y4, _4, g5 = t4 && t4.__k || w, m4 = l4.length;
  for (f5 = T(u5, l4, g5, f5, m4), s4 = 0; s4 < m4; s4++) null != (p4 = u5.__k[s4]) && (h4 = -1 != p4.__i && g5[p4.__i] || d, p4.__i = s4, _4 = q(n3, p4, h4, i4, r4, o4, e4, f5, c4, a4), v4 = p4.__e, p4.ref && h4.ref != p4.ref && (h4.ref && J(h4.ref, null, p4), a4.push(p4.ref, p4.__c || v4, p4)), null == y4 && null != v4 && (y4 = v4), 4 & p4.__u ? (f5 = j(p4, f5, n3), h4.__e && (h4.__e = null)) : "function" == typeof p4.type && void 0 !== _4 ? f5 = _4 : v4 && (f5 = v4.nextSibling), p4.__u &= -7);
  return u5.__e = y4, f5;
}
function T(n3, l4, u5, t4, i4) {
  var r4, o4, e4, f5, c4, a4 = u5.length, s4 = a4, h4 = 0;
  for (n3.__k = new Array(i4), r4 = 0; r4 < i4; r4++) null != (o4 = l4[r4]) && "boolean" != typeof o4 && "function" != typeof o4 ? ("string" == typeof o4 || "number" == typeof o4 || "bigint" == typeof o4 || o4.constructor == String ? o4 = n3.__k[r4] = x(null, o4, null, null, null) : g(o4) ? o4 = n3.__k[r4] = x(S, { children: o4 }, null, null, null) : void 0 === o4.constructor && o4.__b > 0 ? o4 = n3.__k[r4] = x(o4.type, o4.props, o4.key, o4.ref ? o4.ref : null, o4.__v) : n3.__k[r4] = o4, f5 = r4 + h4, o4.__ = n3, o4.__b = n3.__b + 1, e4 = null, -1 != (c4 = o4.__i = O(o4, u5, f5, s4)) && (s4--, (e4 = u5[c4]) && (e4.__u |= 2)), null == e4 || null == e4.__v ? (-1 == c4 && (i4 > a4 ? h4-- : i4 < a4 && h4++), "function" != typeof o4.type && (o4.__u |= 4)) : c4 != f5 && (c4 == f5 - 1 ? h4-- : c4 == f5 + 1 ? h4++ : (c4 > f5 ? h4-- : h4++, o4.__u |= 4))) : n3.__k[r4] = null;
  if (s4) for (r4 = 0; r4 < a4; r4++) null != (e4 = u5[r4]) && 0 == (2 & e4.__u) && (e4.__e == t4 && (t4 = $(e4)), K(e4, e4));
  return t4;
}
function j(n3, l4, u5) {
  var t4, i4;
  if ("function" == typeof n3.type) {
    for (t4 = n3.__k, i4 = 0; t4 && i4 < t4.length; i4++) t4[i4] && (t4[i4].__ = n3, l4 = j(t4[i4], l4, u5));
    return l4;
  }
  n3.__e != l4 && (l4 && n3.type && !l4.parentNode && (l4 = $(n3)), l4 = u5.insertBefore(n3.__e, l4 || null));
  do {
    l4 = l4 && l4.nextSibling;
  } while (null != l4 && 8 == l4.nodeType);
  return l4;
}
function F(n3, l4) {
  return l4 = l4 || [], null == n3 || "boolean" == typeof n3 || (g(n3) ? n3.some(function(n4) {
    F(n4, l4);
  }) : l4.push(n3)), l4;
}
function O(n3, l4, u5, t4) {
  var i4, r4, o4, e4 = n3.key, f5 = n3.type, c4 = l4[u5], a4 = null != c4 && 0 == (2 & c4.__u);
  if (null === c4 && null == e4 || a4 && e4 == c4.key && f5 == c4.type) return u5;
  if (t4 > (a4 ? 1 : 0)) {
    for (i4 = u5 - 1, r4 = u5 + 1; i4 >= 0 || r4 < l4.length; ) if (null != (c4 = l4[o4 = i4 >= 0 ? i4-- : r4++]) && 0 == (2 & c4.__u) && e4 == c4.key && f5 == c4.type) return o4;
  }
  return -1;
}
function z(n3, l4, u5) {
  "-" == l4[0] ? n3.setProperty(l4, null == u5 ? "" : u5) : n3[l4] = null == u5 ? "" : "number" != typeof u5 || _.test(l4) ? u5 : u5 + "px";
}
function N(n3, l4, u5, t4, i4) {
  var r4, o4;
  n: if ("style" == l4) if ("string" == typeof u5) n3.style.cssText = u5;
  else {
    if ("string" == typeof t4 && (n3.style.cssText = t4 = ""), t4) for (l4 in t4) u5 && l4 in u5 || z(n3.style, l4, "");
    if (u5) for (l4 in u5) t4 && u5[l4] == t4[l4] || z(n3.style, l4, u5[l4]);
  }
  else if ("o" == l4[0] && "n" == l4[1]) r4 = l4 != (l4 = l4.replace(s, "$1")), o4 = l4.toLowerCase(), l4 = o4 in n3 || "onFocusOut" == l4 || "onFocusIn" == l4 ? o4.slice(2) : l4.slice(2), n3.l || (n3.l = {}), n3.l[l4 + r4] = u5, u5 ? t4 ? u5[a] = t4[a] : (u5[a] = h, n3.addEventListener(l4, r4 ? v : p, r4)) : n3.removeEventListener(l4, r4 ? v : p, r4);
  else {
    if ("http://www.w3.org/2000/svg" == i4) l4 = l4.replace(/xlink(H|:h)/, "h").replace(/sName$/, "s");
    else if ("width" != l4 && "height" != l4 && "href" != l4 && "list" != l4 && "form" != l4 && "tabIndex" != l4 && "download" != l4 && "rowSpan" != l4 && "colSpan" != l4 && "role" != l4 && "popover" != l4 && l4 in n3) try {
      n3[l4] = null == u5 ? "" : u5;
      break n;
    } catch (n4) {
    }
    "function" == typeof u5 || (null == u5 || false === u5 && "-" != l4[4] ? n3.removeAttribute(l4) : n3.setAttribute(l4, "popover" == l4 && 1 == u5 ? "" : u5));
  }
}
function V(n3) {
  return function(u5) {
    if (this.l) {
      var t4 = this.l[u5.type + n3];
      if (null == u5[c]) u5[c] = h++;
      else if (u5[c] < t4[a]) return;
      return t4(l.event ? l.event(u5) : u5);
    }
  };
}
function q(n3, u5, t4, i4, r4, o4, e4, f5, c4, a4) {
  var s4, h4, p4, v4, y4, d4, _4, k4, x4, M4, I3, P5, A5, H4, T5, j5, F4 = u5.type;
  if (void 0 !== u5.constructor) return null;
  128 & t4.__u && (c4 = !!(32 & t4.__u), o4 = [f5 = u5.__e = t4.__e]), (s4 = l.__b) && s4(u5);
  n: if ("function" == typeof F4) {
    h4 = e4.length;
    try {
      if (x4 = u5.props, M4 = F4.prototype && F4.prototype.render, I3 = (s4 = F4.contextType) && i4[s4.__c], P5 = s4 ? I3 ? I3.props.value : s4.__ : i4, t4.__c ? k4 = (p4 = u5.__c = t4.__c).__ = p4.__E : (M4 ? u5.__c = p4 = new F4(x4, P5) : (u5.__c = p4 = new C(x4, P5), p4.constructor = F4, p4.render = Q), I3 && I3.sub(p4), p4.state || (p4.state = {}), p4.__n = i4, v4 = p4.__d = true, p4.__h = [], p4._sb = []), M4 && null == p4.__s && (p4.__s = p4.state), M4 && null != F4.getDerivedStateFromProps && (p4.__s == p4.state && (p4.__s = m({}, p4.__s)), m(p4.__s, F4.getDerivedStateFromProps(x4, p4.__s))), y4 = p4.props, d4 = p4.state, p4.__v = u5, v4) M4 && null == F4.getDerivedStateFromProps && null != p4.componentWillMount && p4.componentWillMount(), M4 && null != p4.componentDidMount && p4.__h.push(p4.componentDidMount);
      else {
        if (M4 && null == F4.getDerivedStateFromProps && x4 !== y4 && null != p4.componentWillReceiveProps && p4.componentWillReceiveProps(x4, P5), u5.__v == t4.__v || !p4.__e && null != p4.shouldComponentUpdate && false === p4.shouldComponentUpdate(x4, p4.__s, P5)) {
          u5.__v != t4.__v && (p4.props = x4, p4.state = p4.__s, p4.__d = false), u5.__e = t4.__e, u5.__k = t4.__k, u5.__k.some(function(n4) {
            n4 && (n4.__ = u5);
          }), w.push.apply(p4.__h, p4._sb), p4._sb = [], p4.__h.length && e4.push(p4), f5 = $(t4);
          break n;
        }
        null != p4.componentWillUpdate && p4.componentWillUpdate(x4, p4.__s, P5), M4 && null != p4.componentDidUpdate && p4.__h.push(function() {
          p4.componentDidUpdate(y4, d4, _4);
        });
      }
      if (p4.context = P5, p4.props = x4, p4.__P = n3, p4.__e = false, A5 = l.__r, H4 = 0, M4) p4.state = p4.__s, p4.__d = false, A5 && A5(u5), s4 = p4.render(p4.props, p4.state, p4.context), w.push.apply(p4.__h, p4._sb), p4._sb = [];
      else do {
        p4.__d = false, A5 && A5(u5), s4 = p4.render(p4.props, p4.state, p4.context), p4.state = p4.__s;
      } while (p4.__d && ++H4 < 25);
      p4.state = p4.__s, null != p4.getChildContext && (i4 = m(m({}, i4), p4.getChildContext())), M4 && !v4 && null != p4.getSnapshotBeforeUpdate && (_4 = p4.getSnapshotBeforeUpdate(y4, d4)), T5 = null != s4 && s4.type === S && null == s4.key ? E(s4.props.children) : s4, f5 = L(n3, g(T5) ? T5 : [T5], u5, t4, i4, r4, o4, e4, f5, c4, a4), p4.base = u5.__e, u5.__u &= -161, p4.__h.length && e4.push(p4), k4 && (p4.__E = p4.__ = null);
    } catch (n4) {
      if (e4.length = h4, u5.__v = null, c4 || null != o4) {
        if (n4.then) {
          for (u5.__u |= c4 ? 160 : 128; f5 && 8 == f5.nodeType && f5.nextSibling; ) f5 = f5.nextSibling;
          null != o4 && (o4[o4.indexOf(f5)] = null), u5.__e = f5;
        } else if (null != o4) for (j5 = o4.length; j5--; ) b(o4[j5]);
      } else u5.__e = t4.__e;
      null == u5.__k && (u5.__k = t4.__k || []), n4.then || B(u5), l.__e(n4, u5, t4);
    }
  } else null == o4 && u5.__v == t4.__v ? (u5.__k = t4.__k, u5.__e = t4.__e) : f5 = u5.__e = G(t4.__e, u5, t4, i4, r4, o4, e4, c4, a4);
  return (s4 = l.diffed) && s4(u5), 128 & u5.__u ? void 0 : f5;
}
function B(n3) {
  n3 && (n3.__c && (n3.__c.__e = true), n3.__k && n3.__k.some(B));
}
function D(n3, u5, t4) {
  for (var i4 = 0; i4 < t4.length; i4++) J(t4[i4], t4[++i4], t4[++i4]);
  l.__c && l.__c(u5, n3), n3.some(function(u6) {
    try {
      n3 = u6.__h, u6.__h = [], n3.some(function(n4) {
        n4.call(u6);
      });
    } catch (n4) {
      l.__e(n4, u6.__v);
    }
  });
}
function E(n3) {
  return "object" != typeof n3 || null == n3 || n3.__b > 0 ? n3 : g(n3) ? n3.map(E) : void 0 !== n3.constructor ? null : m({}, n3);
}
function G(u5, t4, i4, r4, o4, e4, f5, c4, a4) {
  var s4, h4, p4, v4, y4, w4, _4, m4 = i4.props || d, k4 = t4.props, x4 = t4.type;
  if ("svg" == x4 ? o4 = "http://www.w3.org/2000/svg" : "math" == x4 ? o4 = "http://www.w3.org/1998/Math/MathML" : o4 || (o4 = "http://www.w3.org/1999/xhtml"), null != e4) {
    for (s4 = 0; s4 < e4.length; s4++) if ((y4 = e4[s4]) && "setAttribute" in y4 == !!x4 && (x4 ? y4.localName == x4 : 3 == y4.nodeType)) {
      u5 = y4, e4[s4] = null;
      break;
    }
  }
  if (null == u5) {
    if (null == x4) return document.createTextNode(k4);
    u5 = document.createElementNS(o4, x4, k4.is && k4), c4 && (l.__m && l.__m(t4, e4), c4 = false), e4 = null;
  }
  if (null == x4) m4 === k4 || c4 && u5.data == k4 || (u5.data = k4);
  else {
    if (e4 = "textarea" == x4 && null != k4.defaultValue ? null : e4 && n.call(u5.childNodes), !c4 && null != e4) for (m4 = {}, s4 = 0; s4 < u5.attributes.length; s4++) m4[(y4 = u5.attributes[s4]).name] = y4.value;
    for (s4 in m4) y4 = m4[s4], "dangerouslySetInnerHTML" == s4 ? p4 = y4 : "children" == s4 || s4 in k4 || "value" == s4 && "defaultValue" in k4 || "checked" == s4 && "defaultChecked" in k4 || N(u5, s4, null, y4, o4);
    for (s4 in k4) y4 = k4[s4], "children" == s4 ? v4 = y4 : "dangerouslySetInnerHTML" == s4 ? h4 = y4 : "value" == s4 ? w4 = y4 : "checked" == s4 ? _4 = y4 : c4 && "function" != typeof y4 || m4[s4] === y4 || N(u5, s4, y4, m4[s4], o4);
    if (h4) c4 || p4 && (h4.__html == p4.__html || h4.__html == u5.innerHTML) || (u5.innerHTML = h4.__html), t4.__k = [];
    else if (p4 && (u5.innerHTML = ""), L("template" == t4.type ? u5.content : u5, g(v4) ? v4 : [v4], t4, i4, r4, "foreignObject" == x4 ? "http://www.w3.org/1999/xhtml" : o4, e4, f5, e4 ? e4[0] : i4.__k && $(i4, 0), c4, a4), null != e4) for (s4 = e4.length; s4--; ) b(e4[s4]);
    c4 && "textarea" != x4 || (s4 = "value", "progress" == x4 && null == w4 ? u5.removeAttribute("value") : null != w4 && (w4 !== u5[s4] || "progress" == x4 && !w4 || "option" == x4 && w4 != m4[s4]) && N(u5, s4, w4, m4[s4], o4), s4 = "checked", null != _4 && _4 != u5[s4] && N(u5, s4, _4, m4[s4], o4));
  }
  return u5;
}
function J(n3, u5, t4) {
  try {
    if ("function" == typeof n3) {
      var i4 = "function" == typeof n3.__u;
      i4 && n3.__u(), i4 && null == u5 || (n3.__u = n3(u5));
    } else n3.current = u5;
  } catch (n4) {
    l.__e(n4, t4);
  }
}
function K(n3, u5, t4) {
  var i4, r4;
  if (l.unmount && l.unmount(n3), (i4 = n3.ref) && (i4.current && i4.current != n3.__e || J(i4, null, u5)), null != (i4 = n3.__c)) {
    if (i4.componentWillUnmount) try {
      i4.componentWillUnmount();
    } catch (n4) {
      l.__e(n4, u5);
    }
    i4.base = i4.__P = i4.__n = null;
  }
  if (i4 = n3.__k) for (r4 = 0; r4 < i4.length; r4++) i4[r4] && K(i4[r4], u5, t4 || "function" != typeof n3.type);
  t4 || b(n3.__e), n3.__c = n3.__ = n3.__e = void 0;
}
function Q(n3, l4, u5) {
  return this.constructor(n3, u5);
}
function R(u5, t4, i4) {
  var r4, o4, e4, f5;
  t4 == document && (t4 = document.documentElement), l.__ && l.__(u5, t4), o4 = (r4 = "function" == typeof i4) ? null : i4 && i4.__k || t4.__k, e4 = [], f5 = [], q(t4, u5 = (!r4 && i4 || t4).__k = k(S, null, [u5]), o4 || d, d, t4.namespaceURI, !r4 && i4 ? [i4] : o4 ? null : t4.firstChild ? n.call(t4.childNodes) : null, e4, !r4 && i4 ? i4 : o4 ? o4.__e : t4.firstChild, r4, f5), D(e4, u5, f5), u5.props.children = null;
}
function W(l4, u5, t4) {
  var i4, r4, o4, e4, f5 = m({}, l4.props);
  for (o4 in l4.type && l4.type.defaultProps && (e4 = l4.type.defaultProps), u5) "key" == o4 ? i4 = u5[o4] : "ref" == o4 ? r4 = u5[o4] : f5[o4] = void 0 === u5[o4] && null != e4 ? e4[o4] : u5[o4];
  return arguments.length > 2 && (f5.children = arguments.length > 3 ? n.call(arguments, 2) : t4), x(l4.type, f5, i4 || l4.key, r4 || l4.ref, null);
}
n = w.slice, l = { __e: function(n3, l4, u5, t4) {
  for (var i4, r4, o4; l4 = l4.__; ) if ((i4 = l4.__c) && !i4.__) try {
    if ((r4 = i4.constructor) && null != r4.getDerivedStateFromError && (i4.setState(r4.getDerivedStateFromError(n3)), o4 = i4.__d), null != i4.componentDidCatch && (i4.componentDidCatch(n3, t4 || {}), o4 = i4.__d), o4) return i4.__E = i4;
  } catch (l5) {
    n3 = l5;
  }
  throw n3;
} }, u = 0, t = function(n3) {
  return null != n3 && void 0 === n3.constructor;
}, C.prototype.setState = function(n3, l4) {
  var u5;
  u5 = null != this.__s && this.__s != this.state ? this.__s : this.__s = m({}, this.state), "function" == typeof n3 && (n3 = n3(m({}, u5), this.props)), n3 && m(u5, n3), null != n3 && this.__v && (l4 && this._sb.push(l4), A(this));
}, C.prototype.forceUpdate = function(n3) {
  this.__v && (this.__e = true, n3 && this.__h.push(n3), A(this));
}, C.prototype.render = S, i = [], o = "function" == typeof Promise ? Promise.prototype.then.bind(Promise.resolve()) : setTimeout, e = function(n3, l4) {
  return n3.__v.__b - l4.__v.__b;
}, H.__r = 0, f = Math.random().toString(8), c = "__d" + f, a = "__a" + f, s = /(PointerCapture)$|Capture$/i, h = 0, p = V(false), v = V(true), y = 0;

// node_modules/preact/hooks/dist/hooks.module.js
var t2;
var r2;
var u2;
var i2;
var o2 = 0;
var f2 = [];
var c2 = l;
var e2 = c2.__b;
var a2 = c2.__r;
var v2 = c2.diffed;
var l2 = c2.__c;
var m2 = c2.unmount;
var p2 = c2.__;
function s2(n3, t4) {
  c2.__h && c2.__h(r2, n3, o2 || t4), o2 = 0;
  var u5 = r2.__H || (r2.__H = { __: [], __h: [] });
  return n3 >= u5.__.length && u5.__.push({}), u5.__[n3];
}
function d2(n3) {
  return o2 = 1, y2(D2, n3);
}
function y2(n3, u5, i4) {
  var o4 = s2(t2++, 2);
  if (o4.t = n3, !o4.__c && (o4.__ = [i4 ? i4(u5) : D2(void 0, u5), function(n4) {
    var t4 = o4.__N ? o4.__N[0] : o4.__[0], r4 = o4.t(t4, n4);
    t4 !== r4 && (o4.__N = [r4, o4.__[1]], o4.__c.setState({}));
  }], o4.__c = r2, !r2.__f)) {
    var f5 = function(n4, t4, r4) {
      if (!o4.__c.__H) return true;
      var u6 = false, i5 = o4.__c.props !== n4;
      if (o4.__c.__H.__.some(function(n5) {
        if (n5.__N) {
          u6 = true;
          var t5 = n5.__[0];
          n5.__ = n5.__N, n5.__N = void 0, t5 !== n5.__[0] && (i5 = true);
        }
      }), c4) {
        var f6 = c4.call(this, n4, t4, r4);
        return u6 ? f6 || i5 : f6;
      }
      return !u6 || i5;
    };
    r2.__f = true;
    var c4 = r2.shouldComponentUpdate, e4 = r2.componentWillUpdate;
    r2.componentWillUpdate = function(n4, t4, r4) {
      if (this.__e) {
        var u6 = c4;
        c4 = void 0, f5(n4, t4, r4), c4 = u6;
      }
      e4 && e4.call(this, n4, t4, r4);
    }, r2.shouldComponentUpdate = f5;
  }
  return o4.__N || o4.__;
}
function h2(n3, u5) {
  var i4 = s2(t2++, 3);
  !c2.__s && C2(i4.__H, u5) && (i4.__ = n3, i4.u = u5, r2.__H.__h.push(i4));
}
function A2(n3) {
  return o2 = 5, T2(function() {
    return { current: n3 };
  }, []);
}
function T2(n3, r4) {
  var u5 = s2(t2++, 7);
  return C2(u5.__H, r4) && (u5.__ = n3(), u5.__H = r4, u5.__h = n3), u5.__;
}
function q2(n3, t4) {
  return o2 = 8, T2(function() {
    return n3;
  }, t4);
}
function j2() {
  for (var n3; n3 = f2.shift(); ) {
    var t4 = n3.__H;
    if (n3.__P && t4) try {
      t4.__h.some(z2), t4.__h.some(B2), t4.__h = [];
    } catch (r4) {
      t4.__h = [], c2.__e(r4, n3.__v);
    }
  }
}
c2.__b = function(n3) {
  r2 = null, e2 && e2(n3);
}, c2.__ = function(n3, t4) {
  n3 && t4.__k && t4.__k.__m && (n3.__m = t4.__k.__m), p2 && p2(n3, t4);
}, c2.__r = function(n3) {
  a2 && a2(n3), t2 = 0;
  var i4 = (r2 = n3.__c).__H;
  i4 && (u2 === r2 ? (i4.__h = [], r2.__h = [], i4.__.some(function(n4) {
    n4.__N && (n4.__ = n4.__N), n4.u = n4.__N = void 0;
  })) : (i4.__h.some(z2), i4.__h.some(B2), i4.__h = [], t2 = 0)), u2 = r2;
}, c2.diffed = function(n3) {
  v2 && v2(n3);
  var t4 = n3.__c;
  t4 && t4.__H && (t4.__H.__h.length && (1 !== f2.push(t4) && i2 === c2.requestAnimationFrame || ((i2 = c2.requestAnimationFrame) || w2)(j2)), t4.__H.__.some(function(n4) {
    n4.u && (n4.__H = n4.u, n4.u = void 0);
  })), u2 = r2 = null;
}, c2.__c = function(n3, t4) {
  t4.some(function(n4) {
    try {
      n4.__h.some(z2), n4.__h = n4.__h.filter(function(n5) {
        return !n5.__ || B2(n5);
      });
    } catch (r4) {
      t4.some(function(n5) {
        n5.__h && (n5.__h = []);
      }), t4 = [], c2.__e(r4, n4.__v);
    }
  }), l2 && l2(n3, t4);
}, c2.unmount = function(n3) {
  m2 && m2(n3);
  var t4, r4 = n3.__c;
  r4 && r4.__H && (r4.__H.__.some(function(n4) {
    try {
      z2(n4);
    } catch (n5) {
      t4 = n5;
    }
  }), r4.__H = void 0, t4 && c2.__e(t4, r4.__v));
};
var k2 = "function" == typeof requestAnimationFrame;
function w2(n3) {
  var t4, r4 = function() {
    clearTimeout(u5), k2 && cancelAnimationFrame(t4), setTimeout(n3);
  }, u5 = setTimeout(r4, 35);
  k2 && (t4 = requestAnimationFrame(r4));
}
function z2(n3) {
  var t4 = r2, u5 = n3.__c;
  "function" == typeof u5 && (n3.__c = void 0, u5()), r2 = t4;
}
function B2(n3) {
  var t4 = r2;
  n3.__c = n3.__(), r2 = t4;
}
function C2(n3, t4) {
  return !n3 || n3.length !== t4.length || t4.some(function(t5, r4) {
    return t5 !== n3[r4];
  });
}
function D2(n3, t4) {
  return "function" == typeof t4 ? t4(n3) : t4;
}

// node_modules/preact/compat/dist/compat.module.js
function g3(n3, t4) {
  for (var e4 in t4) n3[e4] = t4[e4];
  return n3;
}
function E2(n3, t4) {
  for (var e4 in n3) if ("__source" !== e4 && !(e4 in t4)) return true;
  for (var r4 in t4) if ("__source" !== r4 && n3[r4] !== t4[r4]) return true;
  return false;
}
function M2(n3, t4) {
  this.props = n3, this.context = t4;
}
(M2.prototype = new C()).isPureReactComponent = true, M2.prototype.shouldComponentUpdate = function(n3, t4) {
  return E2(this.props, n3) || E2(this.state, t4);
};
var T3 = l.__b;
l.__b = function(n3) {
  n3.type && n3.type.__f && n3.ref && (n3.props.ref = n3.ref, n3.ref = null), T3 && T3(n3);
};
var A3 = "undefined" != typeof Symbol && Symbol.for && Symbol.for("react.forward_ref") || 3911;
var O2 = l.__e;
l.__e = function(n3, t4, e4, r4) {
  if (n3.then) {
    for (var u5, o4 = t4; o4 = o4.__; ) if ((u5 = o4.__c) && u5.__c) return null == t4.__e && (t4.__e = e4.__e, t4.__k = e4.__k || []), u5.__c(n3, t4);
  }
  O2(n3, t4, e4, r4);
};
var U2 = l.unmount;
function V2(n3, t4, e4) {
  return n3 && (n3.__c && n3.__c.__H && (n3.__c.__H.__.forEach(function(n4) {
    "function" == typeof n4.__c && n4.__c();
  }), n3.__c.__H = null), null != (n3 = g3({}, n3)).__c && (n3.__c.__P === e4 && (n3.__c.__P = t4), n3.__c.__e = true, n3.__c = null), n3.__k = n3.__k && n3.__k.map(function(n4) {
    return V2(n4, t4, e4);
  })), n3;
}
function W2(n3, t4, e4) {
  return n3 && e4 && (n3.__v = null, n3.__k = n3.__k && n3.__k.map(function(n4) {
    return W2(n4, t4, e4);
  }), n3.__c && n3.__c.__P === t4 && (n3.__e && e4.appendChild(n3.__e), n3.__c.__e = true, n3.__c.__P = e4)), n3;
}
function P3() {
  this.__u = 0, this.o = null, this.__b = null;
}
function j3(n3) {
  var t4 = n3.__ && n3.__.__c;
  return t4 && t4.__a && t4.__a(n3);
}
function B3() {
  this.i = null, this.l = null;
}
l.unmount = function(n3) {
  var t4 = n3.__c;
  t4 && (t4.__z = true), t4 && t4.__R && t4.__R(), t4 && 32 & n3.__u && (n3.type = null), U2 && U2(n3);
}, (P3.prototype = new C()).__c = function(n3, t4) {
  var e4 = t4.__c, r4 = this;
  null == r4.o && (r4.o = []), r4.o.push(e4);
  var u5 = j3(r4.__v), o4 = false, i4 = function() {
    o4 || r4.__z || (o4 = true, e4.__R = null, u5 ? u5(f5) : f5());
  };
  e4.__R = i4;
  var l4 = e4.__P;
  e4.__P = null;
  var f5 = function() {
    if (!--r4.__u) {
      if (r4.state.__a) {
        var n4 = r4.state.__a;
        r4.__v.__k[0] = W2(n4, n4.__c.__P, n4.__c.__O);
      }
      var t5;
      for (r4.setState({ __a: r4.__b = null }); t5 = r4.o.pop(); ) t5.__P = l4, t5.forceUpdate();
    }
  };
  r4.__u++ || 32 & t4.__u || r4.setState({ __a: r4.__b = r4.__v.__k[0] }), n3.then(i4, i4);
}, P3.prototype.componentWillUnmount = function() {
  this.o = [];
}, P3.prototype.render = function(n3, e4) {
  if (this.__b) {
    if (this.__v.__k) {
      var r4 = document.createElement("div"), o4 = this.__v.__k[0].__c;
      this.__v.__k[0] = V2(this.__b, r4, o4.__O = o4.__P);
    }
    this.__b = null;
  }
  var i4 = e4.__a && k(S, null, n3.fallback);
  return i4 && (i4.__u &= -33), [k(S, null, e4.__a ? null : n3.children), i4];
};
var H2 = function(n3, t4, e4) {
  if (++e4[1] === e4[0] && n3.l.delete(t4), n3.props.revealOrder && ("t" !== n3.props.revealOrder[0] || !n3.l.size)) for (e4 = n3.i; e4; ) {
    for (; e4.length > 3; ) e4.pop()();
    if (e4[1] < e4[0]) break;
    n3.i = e4 = e4[2];
  }
};
(B3.prototype = new C()).__a = function(n3) {
  var t4 = this, e4 = j3(t4.__v), r4 = t4.l.get(n3);
  return r4[0]++, function(u5) {
    var o4 = function() {
      t4.props.revealOrder ? (r4.push(u5), H2(t4, n3, r4)) : u5();
    };
    e4 ? e4(o4) : o4();
  };
}, B3.prototype.render = function(n3) {
  this.i = null, this.l = /* @__PURE__ */ new Map();
  var t4 = F(n3.children);
  n3.revealOrder && "b" === n3.revealOrder[0] && t4.reverse();
  for (var e4 = t4.length; e4--; ) this.l.set(t4[e4], this.i = [1, 0, this.i]);
  return n3.children;
}, B3.prototype.componentDidUpdate = B3.prototype.componentDidMount = function() {
  var n3 = this;
  this.l.forEach(function(t4, e4) {
    H2(n3, e4, t4);
  });
};
var q3 = "undefined" != typeof Symbol && Symbol.for && Symbol.for("react.element") || 60103;
var G2 = /^(?:accent|alignment|arabic|baseline|cap|clip(?!PathU)|color|dominant|fill|flood|font|glyph(?!R)|horiz|image(!S)|letter|lighting|marker(?!H|W|U)|overline|paint|pointer|shape|stop|strikethrough|stroke|text(?!L)|transform|underline|unicode|units|v|vector|vert|word|writing|x(?!C))[A-Z]/;
var J2 = /^on(Ani|Tra|Tou|BeforeInp|Compo)/;
var K2 = /[A-Z0-9]/g;
var Q2 = "undefined" != typeof document;
var X2 = function(n3) {
  return ("undefined" != typeof Symbol && "symbol" == typeof Symbol() ? /fil|che|rad/ : /fil|che|ra/).test(n3);
};
function nn(n3, t4, e4) {
  return null == t4.__k && (t4.textContent = ""), R(n3, t4), "function" == typeof e4 && e4(), n3 ? n3.__c : null;
}
C.prototype.isReactComponent = true, ["componentWillMount", "componentWillReceiveProps", "componentWillUpdate"].forEach(function(t4) {
  Object.defineProperty(C.prototype, t4, { configurable: true, get: function() {
    return this["UNSAFE_" + t4];
  }, set: function(n3) {
    Object.defineProperty(this, t4, { configurable: true, writable: true, value: n3 });
  } });
});
var en = l.event;
l.event = function(n3) {
  return en && (n3 = en(n3)), n3.persist = function() {
  }, n3.isPropagationStopped = function() {
    return this.cancelBubble;
  }, n3.isDefaultPrevented = function() {
    return this.defaultPrevented;
  }, n3.nativeEvent = n3;
};
var rn;
var un = { configurable: true, get: function() {
  return this.class;
} };
var on = l.vnode;
l.vnode = function(n3) {
  "string" == typeof n3.type && (function(n4) {
    var t4 = n4.props, e4 = n4.type, u5 = {}, o4 = -1 == e4.indexOf("-");
    for (var i4 in t4) {
      var l4 = t4[i4];
      if (!("value" === i4 && "defaultValue" in t4 && null == l4 || Q2 && "children" === i4 && "noscript" === e4 || "class" === i4 || "className" === i4)) {
        var f5 = i4.toLowerCase();
        "defaultValue" === i4 && "value" in t4 && null == t4.value ? i4 = "value" : "download" === i4 && true === l4 ? l4 = "" : "translate" === f5 && "no" === l4 ? l4 = false : "o" === f5[0] && "n" === f5[1] ? "ondoubleclick" === f5 ? i4 = "ondblclick" : "onchange" !== f5 || "input" !== e4 && "textarea" !== e4 || X2(t4.type) ? "onfocus" === f5 ? i4 = "onfocusin" : "onblur" === f5 ? i4 = "onfocusout" : J2.test(i4) && (i4 = f5) : f5 = i4 = "oninput" : o4 && G2.test(i4) ? i4 = i4.replace(K2, "-$&").toLowerCase() : null === l4 && (l4 = void 0), "oninput" === f5 && u5[i4 = f5] && (i4 = "oninputCapture"), u5[i4] = l4;
      }
    }
    "select" == e4 && (u5.multiple && Array.isArray(u5.value) && (u5.value = F(t4.children).forEach(function(n5) {
      n5.props.selected = -1 != u5.value.indexOf(n5.props.value);
    })), null != u5.defaultValue && (u5.value = F(t4.children).forEach(function(n5) {
      n5.props.selected = u5.multiple ? -1 != u5.defaultValue.indexOf(n5.props.value) : u5.defaultValue == n5.props.value;
    }))), t4.class && !t4.className ? (u5.class = t4.class, Object.defineProperty(u5, "className", un)) : t4.className && (u5.class = u5.className = t4.className), n4.props = u5;
  })(n3), n3.$$typeof = q3, on && on(n3);
};
var ln = l.__r;
l.__r = function(n3) {
  ln && ln(n3), rn = n3.__c;
};
var fn = l.diffed;
l.diffed = function(n3) {
  fn && fn(n3);
  var t4 = n3.props, e4 = n3.__e;
  null != e4 && "textarea" === n3.type && "value" in t4 && t4.value !== e4.value && (e4.value = null == t4.value ? "" : t4.value), rn = null;
};

// node_modules/@uppy/core/lib/UIPlugin.js
function debounce(fn2) {
  let calling = null;
  let latestArgs;
  return (...args) => {
    latestArgs = args;
    if (!calling) {
      calling = Promise.resolve().then(() => {
        calling = null;
        return fn2(...latestArgs);
      });
    }
    return calling;
  };
}
var _updateUI;
var _UIPlugin = class _UIPlugin extends BasePlugin {
  constructor() {
    super(...arguments);
    __privateAdd(this, _updateUI);
    __publicField(this, "isTargetDOMEl");
    __publicField(this, "el");
    __publicField(this, "parent");
    __publicField(this, "title");
  }
  getTargetPlugin(target) {
    let targetPlugin;
    if (typeof target?.addTarget === "function") {
      targetPlugin = target;
      if (!(targetPlugin instanceof _UIPlugin)) {
        console.warn(new Error("The provided plugin is not an instance of UIPlugin. This is an indication of a bug with the way Uppy is bundled.", { cause: { targetPlugin, UIPlugin: _UIPlugin } }));
      }
    } else if (typeof target === "function") {
      const Target = target;
      this.uppy.iteratePlugins((p4) => {
        if (p4 instanceof Target) {
          targetPlugin = p4;
        }
      });
    }
    return targetPlugin;
  }
  /**
   * Check if supplied `target` is a DOM element or an `object`.
   * If it’s an object — target is a plugin, and we search `plugins`
   * for a plugin with same name and return its target.
   */
  mount(target, plugin) {
    const callerPluginName = plugin.id;
    const targetElement = findDOMElement_default(target);
    if (targetElement) {
      this.isTargetDOMEl = true;
      const uppyRootElement = document.createElement("div");
      uppyRootElement.classList.add("uppy-Root");
      __privateSet(this, _updateUI, debounce((state) => {
        if (!this.uppy.getPlugin(this.id))
          return;
        nn(this.render(state, uppyRootElement), uppyRootElement);
        this.afterUpdate();
      }));
      this.uppy.log(`Installing ${callerPluginName} to a DOM element '${target}'`);
      if (this.opts.replaceTargetContent) {
        targetElement.innerHTML = "";
      }
      nn(this.render(this.uppy.getState(), uppyRootElement), uppyRootElement);
      this.el = uppyRootElement;
      targetElement.appendChild(uppyRootElement);
      uppyRootElement.dir = this.opts.direction || getTextDirection_default(uppyRootElement) || "ltr";
      this.onMount();
      return this.el;
    }
    const targetPlugin = this.getTargetPlugin(target);
    if (targetPlugin) {
      this.uppy.log(`Installing ${callerPluginName} to ${targetPlugin.id}`);
      this.parent = targetPlugin;
      this.el = targetPlugin.addTarget(plugin);
      this.onMount();
      return this.el;
    }
    this.uppy.log(`Not installing ${callerPluginName}`);
    let message = `Invalid target option given to ${callerPluginName}.`;
    if (typeof target === "function") {
      message += " The given target is not a Plugin class. Please check that you're not specifying a React Component instead of a plugin. If you are using @uppy/* packages directly, make sure you have only 1 version of @uppy/core installed: run `npm ls @uppy/core` on the command line and verify that all the versions match and are deduped correctly.";
    } else {
      message += "If you meant to target an HTML element, please make sure that the element exists. Check that the <script> tag initializing Uppy is right before the closing </body> tag at the end of the page. (see https://github.com/transloadit/uppy/issues/1042)\n\nIf you meant to target a plugin, please confirm that your `import` statements or `require` calls are correct.";
    }
    throw new Error(message);
  }
  /**
   * Called when plugin is mounted, whether in DOM or into another plugin.
   * Needed because sometimes plugins are mounted separately/after `install`,
   * so this.el and this.parent might not be available in `install`.
   * This is the case with @uppy/react plugins, for example.
   */
  render(state, container) {
    throw new Error("Extend the render method to add your plugin to a DOM element");
  }
  update(state) {
    var _a;
    if (this.el != null) {
      (_a = __privateGet(this, _updateUI)) == null ? void 0 : _a.call(this, state);
    }
  }
  unmount() {
    if (this.isTargetDOMEl) {
      this.el?.remove();
    }
    this.onUnmount();
  }
  onMount() {
  }
  onUnmount() {
  }
};
_updateUI = new WeakMap();
var UIPlugin = _UIPlugin;
var UIPlugin_default = UIPlugin;

// node_modules/@uppy/store-default/package.json
var package_default = {
  name: "@uppy/store-default",
  description: "The default simple object-based store for Uppy.",
  version: "4.3.2",
  license: "MIT",
  main: "lib/index.js",
  type: "module",
  scripts: {
    build: "tsc --build tsconfig.build.json",
    typecheck: "tsc --build",
    test: "vitest run --environment=jsdom --silent='passed-only'"
  },
  keywords: [
    "file uploader",
    "uppy",
    "uppy-store"
  ],
  homepage: "https://uppy.io",
  bugs: {
    url: "https://github.com/transloadit/uppy/issues"
  },
  devDependencies: {
    jsdom: "^26.1.0",
    typescript: "^5.8.3",
    vitest: "^3.2.4"
  },
  repository: {
    type: "git",
    url: "git+https://github.com/transloadit/uppy.git"
  },
  files: [
    "src",
    "lib",
    "dist",
    "CHANGELOG.md"
  ]
};

// node_modules/@uppy/store-default/lib/index.js
var _callbacks, _DefaultStore_instances, publish_fn;
var DefaultStore = class {
  constructor() {
    __privateAdd(this, _DefaultStore_instances);
    __publicField(this, "state", {});
    __privateAdd(this, _callbacks, /* @__PURE__ */ new Set());
  }
  getState() {
    return this.state;
  }
  setState(patch) {
    const prevState = { ...this.state };
    const nextState = { ...this.state, ...patch };
    this.state = nextState;
    __privateMethod(this, _DefaultStore_instances, publish_fn).call(this, prevState, nextState, patch);
  }
  subscribe(listener) {
    __privateGet(this, _callbacks).add(listener);
    return () => {
      __privateGet(this, _callbacks).delete(listener);
    };
  }
};
_callbacks = new WeakMap();
_DefaultStore_instances = new WeakSet();
publish_fn = function(...args) {
  __privateGet(this, _callbacks).forEach((listener) => {
    listener(...args);
  });
};
__publicField(DefaultStore, "VERSION", package_default.version);
var lib_default = DefaultStore;

// node_modules/@uppy/utils/lib/getFileNameAndExtension.js
function getFileNameAndExtension(fullFileName) {
  const lastDot = fullFileName.lastIndexOf(".");
  if (lastDot === -1 || lastDot === fullFileName.length - 1) {
    return {
      name: fullFileName,
      extension: void 0
    };
  }
  return {
    name: fullFileName.slice(0, lastDot),
    extension: fullFileName.slice(lastDot + 1)
  };
}

// node_modules/@uppy/utils/lib/mimeTypes.js
var mimeTypes_default = {
  __proto__: null,
  md: "text/markdown",
  markdown: "text/markdown",
  mp4: "video/mp4",
  mp3: "audio/mp3",
  svg: "image/svg+xml",
  jpg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
  gif: "image/gif",
  heic: "image/heic",
  heif: "image/heif",
  yaml: "text/yaml",
  yml: "text/yaml",
  csv: "text/csv",
  tsv: "text/tab-separated-values",
  tab: "text/tab-separated-values",
  avi: "video/x-msvideo",
  mks: "video/x-matroska",
  mkv: "video/x-matroska",
  mov: "video/quicktime",
  dicom: "application/dicom",
  doc: "application/msword",
  msg: "application/vnd.ms-outlook",
  docm: "application/vnd.ms-word.document.macroenabled.12",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  dot: "application/msword",
  dotm: "application/vnd.ms-word.template.macroenabled.12",
  dotx: "application/vnd.openxmlformats-officedocument.wordprocessingml.template",
  xla: "application/vnd.ms-excel",
  xlam: "application/vnd.ms-excel.addin.macroenabled.12",
  xlc: "application/vnd.ms-excel",
  xlf: "application/x-xliff+xml",
  xlm: "application/vnd.ms-excel",
  xls: "application/vnd.ms-excel",
  xlsb: "application/vnd.ms-excel.sheet.binary.macroenabled.12",
  xlsm: "application/vnd.ms-excel.sheet.macroenabled.12",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  xlt: "application/vnd.ms-excel",
  xltm: "application/vnd.ms-excel.template.macroenabled.12",
  xltx: "application/vnd.openxmlformats-officedocument.spreadsheetml.template",
  xlw: "application/vnd.ms-excel",
  txt: "text/plain",
  text: "text/plain",
  conf: "text/plain",
  log: "text/plain",
  pdf: "application/pdf",
  zip: "application/zip",
  "7z": "application/x-7z-compressed",
  rar: "application/x-rar-compressed",
  tar: "application/x-tar",
  gz: "application/gzip",
  dmg: "application/x-apple-diskimage"
};

// node_modules/@uppy/utils/lib/getFileType.js
function getFileType(file) {
  if (file.type)
    return file.type;
  const fileExtension = file.name ? getFileNameAndExtension(file.name).extension?.toLowerCase() : null;
  if (fileExtension && fileExtension in mimeTypes_default) {
    return mimeTypes_default[fileExtension];
  }
  return "application/octet-stream";
}

// node_modules/@uppy/utils/lib/generateFileID.js
function encodeCharacter(character) {
  return character.charCodeAt(0).toString(32);
}
function encodeFilename(name) {
  let suffix = "";
  return name.replace(/[^A-Z0-9]/gi, (character) => {
    suffix += `-${encodeCharacter(character)}`;
    return "/";
  }) + suffix;
}
function generateFileID(file, instanceId) {
  let id = instanceId || "uppy";
  if (typeof file.name === "string") {
    id += `-${encodeFilename(file.name.toLowerCase())}`;
  }
  if (file.type !== void 0) {
    id += `-${file.type}`;
  }
  if (file.meta && typeof file.meta.relativePath === "string") {
    id += `-${encodeFilename(file.meta.relativePath.toLowerCase())}`;
  }
  if (file.data.size !== void 0) {
    id += `-${file.data.size}`;
  }
  if (file.data.lastModified !== void 0) {
    id += `-${file.data.lastModified}`;
  }
  return id;
}
function hasFileStableId(file) {
  if (!file.isRemote || !file.remote)
    return false;
  const stableIdProviders = /* @__PURE__ */ new Set([
    "box",
    "dropbox",
    "drive",
    "facebook",
    "unsplash"
  ]);
  return stableIdProviders.has(file.remote.provider);
}
function getSafeFileId(file, instanceId) {
  if (hasFileStableId(file))
    return file.id;
  const fileType = getFileType(file);
  return generateFileID({
    ...file,
    type: fileType
  }, instanceId);
}

// node_modules/@uppy/core/lib/Uppy.js
var import_throttle = __toESM(require_throttle(), 1);
var import_namespace_emitter = __toESM(require_namespace_emitter(), 1);

// node_modules/@uppy/core/node_modules/nanoid/non-secure/index.js
var urlAlphabet = "useandom-26T198340PX75pxJACKVERYMINDBUSHWOLF_GQZbfghjklqvwyzrict";
var nanoid = (size = 21) => {
  let id = "";
  let i4 = size | 0;
  while (i4-- > 0) {
    id += urlAlphabet[Math.random() * 64 | 0];
  }
  return id;
};

// node_modules/@uppy/core/package.json
var package_default2 = {
  name: "@uppy/core",
  description: "Core module for the extensible JavaScript file upload widget with support for drag&drop, resumable uploads, previews, restrictions, file processing/encoding, remote providers like Instagram, Dropbox, Google Drive, S3 and more :dog:",
  version: "4.5.3",
  license: "MIT",
  main: "lib/index.js",
  style: "dist/style.min.css",
  type: "module",
  sideEffects: [
    "*.css"
  ],
  scripts: {
    build: "tsc --build tsconfig.build.json",
    "build:css": "sass --load-path=../../ src/style.scss dist/style.css && postcss dist/style.css -u cssnano -o dist/style.min.css",
    typecheck: "tsc --build",
    test: "vitest run --environment=jsdom --silent='passed-only'"
  },
  keywords: [
    "file uploader",
    "uppy",
    "uppy-plugin"
  ],
  homepage: "https://uppy.io",
  bugs: {
    url: "https://github.com/transloadit/uppy/issues"
  },
  repository: {
    type: "git",
    url: "git+https://github.com/transloadit/uppy.git"
  },
  files: [
    "src",
    "lib",
    "dist",
    "CHANGELOG.md"
  ],
  dependencies: {
    "@transloadit/prettier-bytes": "^0.3.4",
    "@uppy/store-default": "^4.3.2",
    "@uppy/utils": "^6.2.2",
    lodash: "^4.17.21",
    "mime-match": "^1.0.2",
    "namespace-emitter": "^2.0.1",
    nanoid: "^5.0.9",
    preact: "^10.5.13"
  },
  devDependencies: {
    "@types/deep-freeze": "^0",
    cssnano: "^7.0.7",
    "deep-freeze": "^0.0.1",
    jsdom: "^26.1.0",
    postcss: "^8.5.6",
    "postcss-cli": "^11.0.1",
    sass: "^1.89.2",
    typescript: "^5.8.3",
    vitest: "^3.2.4"
  }
};

// node_modules/@uppy/core/lib/getFileName.js
function getFileName(fileType, fileDescriptor) {
  if (fileDescriptor.name) {
    return fileDescriptor.name;
  }
  if (fileType.split("/")[0] === "image") {
    return `${fileType.split("/")[0]}.${fileType.split("/")[1]}`;
  }
  return "noname";
}

// node_modules/@uppy/core/lib/locale.js
var locale_default = {
  strings: {
    addBulkFilesFailed: {
      0: "Failed to add %{smart_count} file due to an internal error",
      1: "Failed to add %{smart_count} files due to internal errors"
    },
    youCanOnlyUploadX: {
      0: "You can only upload %{smart_count} file",
      1: "You can only upload %{smart_count} files"
    },
    youHaveToAtLeastSelectX: {
      0: "You have to select at least %{smart_count} file",
      1: "You have to select at least %{smart_count} files"
    },
    aggregateExceedsSize: "You selected %{size} of files, but maximum allowed size is %{sizeAllowed}",
    exceedsSize: "%{file} exceeds maximum allowed size of %{size}",
    missingRequiredMetaField: "Missing required meta fields",
    missingRequiredMetaFieldOnFile: "Missing required meta fields in %{fileName}",
    inferiorSize: "This file is smaller than the allowed size of %{size}",
    youCanOnlyUploadFileTypes: "You can only upload: %{types}",
    noMoreFilesAllowed: "Cannot add more files",
    noDuplicates: "Cannot add the duplicate file '%{fileName}', it already exists",
    companionError: "Connection with Companion failed",
    authAborted: "Authentication aborted",
    companionUnauthorizeHint: "To unauthorize to your %{provider} account, please go to %{url}",
    failedToUpload: "Failed to upload %{file}",
    noInternetConnection: "No Internet connection",
    connectedToInternet: "Connected to the Internet",
    // Strings for remote providers
    noFilesFound: "You have no files or folders here",
    noSearchResults: "Unfortunately, there are no results for this search",
    selectX: {
      0: "Select %{smart_count}",
      1: "Select %{smart_count}"
    },
    allFilesFromFolderNamed: "All files from folder %{name}",
    openFolderNamed: "Open folder %{name}",
    cancel: "Cancel",
    logOut: "Log out",
    logIn: "Log in",
    pickFiles: "Pick files",
    pickPhotos: "Pick photos",
    filter: "Filter",
    resetFilter: "Reset filter",
    loading: "Loading...",
    loadedXFiles: "Loaded %{numFiles} files",
    authenticateWithTitle: "Please authenticate with %{pluginName} to select files",
    authenticateWith: "Connect to %{pluginName}",
    signInWithGoogle: "Sign in with Google",
    searchImages: "Search for images",
    enterTextToSearch: "Enter text to search for images",
    search: "Search",
    resetSearch: "Reset search",
    emptyFolderAdded: "No files were added from empty folder",
    addedNumFiles: "Added %{numFiles} file(s)",
    folderAlreadyAdded: 'The folder "%{folder}" was already added',
    folderAdded: {
      0: "Added %{smart_count} file from %{folder}",
      1: "Added %{smart_count} files from %{folder}"
    },
    additionalRestrictionsFailed: "%{count} additional restrictions were not fulfilled",
    unnamed: "Unnamed",
    pleaseWait: "Please wait"
  }
};

// node_modules/@uppy/core/lib/Restricter.js
var import_prettier_bytes = __toESM(require_prettierBytes(), 1);
var import_mime_match = __toESM(require_mime_match(), 1);
var defaultOptions = {
  maxFileSize: null,
  minFileSize: null,
  maxTotalFileSize: null,
  maxNumberOfFiles: null,
  minNumberOfFiles: null,
  allowedFileTypes: null,
  requiredMetaFields: []
};
var RestrictionError = class extends Error {
  constructor(message, opts) {
    super(message);
    __publicField(this, "isUserFacing");
    __publicField(this, "file");
    __publicField(this, "isRestriction", true);
    this.isUserFacing = opts?.isUserFacing ?? true;
    if (opts?.file) {
      this.file = opts.file;
    }
  }
};
var Restricter = class {
  constructor(getOpts, getI18n) {
    __publicField(this, "getI18n");
    __publicField(this, "getOpts");
    this.getI18n = getI18n;
    this.getOpts = () => {
      const opts = getOpts();
      if (opts.restrictions?.allowedFileTypes != null && !Array.isArray(opts.restrictions.allowedFileTypes)) {
        throw new TypeError("`restrictions.allowedFileTypes` must be an array");
      }
      return opts;
    };
  }
  // Because these operations are slow, we cannot run them for every file (if we are adding multiple files)
  validateAggregateRestrictions(existingFiles, addingFiles) {
    const { maxTotalFileSize, maxNumberOfFiles } = this.getOpts().restrictions;
    if (maxNumberOfFiles) {
      const nonGhostFiles = existingFiles.filter((f5) => !f5.isGhost);
      if (nonGhostFiles.length + addingFiles.length > maxNumberOfFiles) {
        throw new RestrictionError(`${this.getI18n()("youCanOnlyUploadX", {
          smart_count: maxNumberOfFiles
        })}`);
      }
    }
    if (maxTotalFileSize) {
      const totalFilesSize = [...existingFiles, ...addingFiles].reduce((total, f5) => total + (f5.size ?? 0), 0);
      if (totalFilesSize > maxTotalFileSize) {
        throw new RestrictionError(this.getI18n()("aggregateExceedsSize", {
          sizeAllowed: (0, import_prettier_bytes.default)(maxTotalFileSize),
          size: (0, import_prettier_bytes.default)(totalFilesSize)
        }));
      }
    }
  }
  validateSingleFile(file) {
    const { maxFileSize, minFileSize, allowedFileTypes } = this.getOpts().restrictions;
    if (allowedFileTypes) {
      const isCorrectFileType = allowedFileTypes.some((type) => {
        if (type.includes("/")) {
          if (!file.type)
            return false;
          return (0, import_mime_match.default)(file.type.replace(/;.*?$/, ""), type);
        }
        if (type[0] === "." && file.extension) {
          return file.extension.toLowerCase() === type.slice(1).toLowerCase();
        }
        return false;
      });
      if (!isCorrectFileType) {
        const allowedFileTypesString = allowedFileTypes.join(", ");
        throw new RestrictionError(this.getI18n()("youCanOnlyUploadFileTypes", {
          types: allowedFileTypesString
        }), { file });
      }
    }
    if (maxFileSize && file.size != null && file.size > maxFileSize) {
      throw new RestrictionError(this.getI18n()("exceedsSize", {
        size: (0, import_prettier_bytes.default)(maxFileSize),
        file: file.name ?? this.getI18n()("unnamed")
      }), { file });
    }
    if (minFileSize && file.size != null && file.size < minFileSize) {
      throw new RestrictionError(this.getI18n()("inferiorSize", {
        size: (0, import_prettier_bytes.default)(minFileSize)
      }), { file });
    }
  }
  validate(existingFiles, addingFiles) {
    addingFiles.forEach((addingFile) => {
      this.validateSingleFile(addingFile);
    });
    this.validateAggregateRestrictions(existingFiles, addingFiles);
  }
  validateMinNumberOfFiles(files) {
    const { minNumberOfFiles } = this.getOpts().restrictions;
    if (minNumberOfFiles && Object.keys(files).length < minNumberOfFiles) {
      throw new RestrictionError(this.getI18n()("youHaveToAtLeastSelectX", {
        smart_count: minNumberOfFiles
      }));
    }
  }
  getMissingRequiredMetaFields(file) {
    const error = new RestrictionError(this.getI18n()("missingRequiredMetaFieldOnFile", {
      fileName: file.name ?? this.getI18n()("unnamed")
    }));
    const { requiredMetaFields } = this.getOpts().restrictions;
    const missingFields = [];
    for (const field of requiredMetaFields) {
      if (!Object.hasOwn(file.meta, field) || file.meta[field] === "") {
        missingFields.push(field);
      }
    }
    return { missingFields, error };
  }
};

// node_modules/@uppy/core/lib/supportsUploadProgress.js
function supportsUploadProgress(userAgent) {
  if (userAgent == null && typeof navigator !== "undefined") {
    userAgent = navigator.userAgent;
  }
  if (!userAgent)
    return true;
  const m4 = /Edge\/(\d+\.\d+)/.exec(userAgent);
  if (!m4)
    return true;
  const edgeVersion = m4[1];
  const version = edgeVersion.split(".", 2);
  const major = parseInt(version[0], 10);
  const minor = parseInt(version[1], 10);
  if (major < 15 || major === 15 && minor < 15063) {
    return true;
  }
  if (major > 18 || major === 18 && minor >= 18218) {
    return true;
  }
  return false;
}

// node_modules/@uppy/core/lib/Uppy.js
var defaultUploadState = {
  totalProgress: 0,
  allowNewUpload: true,
  error: null,
  recoveredState: null
};
var _plugins, _restricter, _storeUnsubscribe, _emitter, _preProcessors, _uploaders, _postProcessors, _Uppy_instances, informAndEmit_fn, checkRequiredMetaFieldsOnFile_fn, checkRequiredMetaFields_fn, assertNewUploadAllowed_fn, transformFile_fn, startIfAutoProceed_fn, checkAndUpdateFileState_fn, getFilesToRetry_fn, doRetryAll_fn, _handleUploadProgress, updateTotalProgress_fn, _updateTotalProgressThrottled, calculateTotalProgress_fn, addListeners_fn, _updateOnlineStatus, _requestClientById, createUpload_fn, getUpload_fn, removeUpload_fn, runUpload_fn;
var _Uppy = class _Uppy {
  /**
   * Instantiate Uppy
   */
  constructor(opts) {
    __privateAdd(this, _Uppy_instances);
    __privateAdd(this, _plugins, /* @__PURE__ */ Object.create(null));
    __privateAdd(this, _restricter);
    __privateAdd(this, _storeUnsubscribe);
    __privateAdd(this, _emitter, (0, import_namespace_emitter.default)());
    __privateAdd(this, _preProcessors, /* @__PURE__ */ new Set());
    __privateAdd(this, _uploaders, /* @__PURE__ */ new Set());
    __privateAdd(this, _postProcessors, /* @__PURE__ */ new Set());
    __publicField(this, "defaultLocale");
    __publicField(this, "locale");
    // The user optionally passes in options, but we set defaults for missing options.
    // We consider all options present after the contructor has run.
    __publicField(this, "opts");
    __publicField(this, "store");
    // Warning: do not use this from a plugin, as it will cause the plugins' translations to be missing
    __publicField(this, "i18n");
    __publicField(this, "i18nArray");
    __publicField(this, "scheduledAutoProceed", null);
    __publicField(this, "wasOffline", false);
    __privateAdd(this, _handleUploadProgress, (file, progress) => {
      const fileInState = file ? this.getFile(file.id) : void 0;
      if (file == null || !fileInState) {
        this.log(`Not setting progress for a file that has been removed: ${file?.id}`);
        return;
      }
      if (fileInState.progress.percentage === 100) {
        this.log(`Not setting progress for a file that has been already uploaded: ${file.id}`);
        return;
      }
      const newProgress = {
        bytesTotal: progress.bytesTotal,
        // bytesTotal may be null or zero; in that case we can't divide by it
        percentage: progress.bytesTotal != null && Number.isFinite(progress.bytesTotal) && progress.bytesTotal > 0 ? Math.round(progress.bytesUploaded / progress.bytesTotal * 100) : void 0
      };
      if (fileInState.progress.uploadStarted != null) {
        this.setFileState(file.id, {
          progress: {
            ...fileInState.progress,
            ...newProgress,
            bytesUploaded: progress.bytesUploaded
          }
        });
      } else {
        this.setFileState(file.id, {
          progress: {
            ...fileInState.progress,
            ...newProgress
          }
        });
      }
      __privateGet(this, _updateTotalProgressThrottled).call(this);
    });
    // ___Why throttle at 500ms?
    //    - We must throttle at >250ms for superfocus in Dashboard to work well
    //    (because animation takes 0.25s, and we want to wait for all animations to be over before refocusing).
    //    [Practical Check]: if thottle is at 100ms, then if you are uploading a file,
    //    and click 'ADD MORE FILES', - focus won't activate in Firefox.
    //    - We must throttle at around >500ms to avoid performance lags.
    //    [Practical Check] Firefox, try to upload a big file for a prolonged period of time. Laptop will start to heat up.
    __privateAdd(this, _updateTotalProgressThrottled, (0, import_throttle.default)(() => __privateMethod(this, _Uppy_instances, updateTotalProgress_fn).call(this), 500, { leading: true, trailing: true }));
    __privateAdd(this, _updateOnlineStatus, this.updateOnlineStatus.bind(this));
    // We need to store request clients by a unique ID, so we can share RequestClient instances across files
    // this allows us to do rate limiting and synchronous operations like refreshing provider tokens
    // example: refreshing tokens: if each file has their own requestclient,
    // we don't have any way to synchronize all requests in order to
    // - block all requests
    // - refresh the token
    // - unblock all requests and allow them to run with a the new access token
    // back when we had a requestclient per file, once an access token expired,
    // all 6 files would go ahead and refresh the token at the same time
    // (calling /refresh-token up to 6 times), which will probably fail for some providers
    __privateAdd(this, _requestClientById, /* @__PURE__ */ new Map());
    this.defaultLocale = locale_default;
    const defaultOptions8 = {
      id: "uppy",
      autoProceed: false,
      allowMultipleUploadBatches: true,
      debug: false,
      restrictions: defaultOptions,
      meta: {},
      onBeforeFileAdded: (file, files) => !Object.hasOwn(files, file.id),
      onBeforeUpload: (files) => files,
      store: new lib_default(),
      logger: justErrorsLogger,
      infoTimeout: 5e3
    };
    const merged = { ...defaultOptions8, ...opts };
    this.opts = {
      ...merged,
      restrictions: {
        ...defaultOptions8.restrictions,
        ...opts?.restrictions
      }
    };
    if (opts?.logger && opts.debug) {
      this.log("You are using a custom `logger`, but also set `debug: true`, which uses built-in logger to output logs to console. Ignoring `debug: true` and using your custom `logger`.", "warning");
    } else if (opts?.debug) {
      this.opts.logger = debugLogger;
    }
    this.log(`Using Core v${_Uppy.VERSION}`);
    this.i18nInit();
    this.store = this.opts.store;
    this.setState({
      ...defaultUploadState,
      plugins: {},
      files: {},
      currentUploads: {},
      capabilities: {
        uploadProgress: supportsUploadProgress(),
        individualCancellation: true,
        resumableUploads: false
      },
      meta: { ...this.opts.meta },
      info: []
    });
    __privateSet(this, _restricter, new Restricter(() => this.opts, () => this.i18n));
    __privateSet(this, _storeUnsubscribe, this.store.subscribe((prevState, nextState, patch) => {
      this.emit("state-update", prevState, nextState, patch);
      this.updateAll(nextState);
    }));
    if (this.opts.debug && typeof window !== "undefined") {
      window[this.opts.id] = this;
    }
    __privateMethod(this, _Uppy_instances, addListeners_fn).call(this);
  }
  emit(event, ...args) {
    __privateGet(this, _emitter).emit(event, ...args);
  }
  on(event, callback) {
    __privateGet(this, _emitter).on(event, callback);
    return this;
  }
  once(event, callback) {
    __privateGet(this, _emitter).once(event, callback);
    return this;
  }
  off(event, callback) {
    __privateGet(this, _emitter).off(event, callback);
    return this;
  }
  /**
   * Iterate on all plugins and run `update` on them.
   * Called each time state changes.
   *
   */
  updateAll(state) {
    this.iteratePlugins((plugin) => {
      plugin.update(state);
    });
  }
  /**
   * Updates state with a patch
   */
  setState(patch) {
    this.store.setState(patch);
  }
  /**
   * Returns current state.
   */
  getState() {
    return this.store.getState();
  }
  patchFilesState(filesWithNewState) {
    const existingFilesState = this.getState().files;
    this.setState({
      files: {
        ...existingFilesState,
        ...Object.fromEntries(Object.entries(filesWithNewState).map(([fileID, newFileState]) => [
          fileID,
          {
            ...existingFilesState[fileID],
            ...newFileState
          }
        ]))
      }
    });
  }
  /**
   * Shorthand to set state for a specific file.
   */
  setFileState(fileID, state) {
    if (!this.getState().files[fileID]) {
      throw new Error(`Can\u2019t set state for ${fileID} (the file could have been removed)`);
    }
    this.patchFilesState({ [fileID]: state });
  }
  i18nInit() {
    const onMissingKey = (key) => this.log(`Missing i18n string: ${key}`, "error");
    const translator = new Translator([this.defaultLocale, this.opts.locale], {
      onMissingKey
    });
    this.i18n = translator.translate.bind(translator);
    this.i18nArray = translator.translateArray.bind(translator);
    this.locale = translator.locale;
  }
  setOptions(newOpts) {
    this.opts = {
      ...this.opts,
      ...newOpts,
      restrictions: {
        ...this.opts.restrictions,
        ...newOpts?.restrictions
      }
    };
    if (newOpts.meta) {
      this.setMeta(newOpts.meta);
    }
    this.i18nInit();
    if (newOpts.locale) {
      this.iteratePlugins((plugin) => {
        plugin.setOptions(newOpts);
      });
    }
    this.setState(void 0);
  }
  resetProgress() {
    const defaultProgress = {
      percentage: 0,
      bytesUploaded: false,
      uploadComplete: false,
      uploadStarted: null
    };
    const files = { ...this.getState().files };
    const updatedFiles = /* @__PURE__ */ Object.create(null);
    Object.keys(files).forEach((fileID) => {
      updatedFiles[fileID] = {
        ...files[fileID],
        progress: {
          ...files[fileID].progress,
          ...defaultProgress
        },
        // @ts-expect-error these typed are inserted
        // into the namespace in their respective packages
        // but core isn't ware of those
        tus: void 0,
        transloadit: void 0
      };
    });
    this.setState({ files: updatedFiles, ...defaultUploadState });
  }
  clear() {
    const { capabilities, currentUploads } = this.getState();
    if (Object.keys(currentUploads).length > 0 && !capabilities.individualCancellation) {
      throw new Error("The installed uploader plugin does not allow removing files during an upload.");
    }
    this.setState({ ...defaultUploadState, files: {} });
  }
  addPreProcessor(fn2) {
    __privateGet(this, _preProcessors).add(fn2);
  }
  removePreProcessor(fn2) {
    return __privateGet(this, _preProcessors).delete(fn2);
  }
  addPostProcessor(fn2) {
    __privateGet(this, _postProcessors).add(fn2);
  }
  removePostProcessor(fn2) {
    return __privateGet(this, _postProcessors).delete(fn2);
  }
  addUploader(fn2) {
    __privateGet(this, _uploaders).add(fn2);
  }
  removeUploader(fn2) {
    return __privateGet(this, _uploaders).delete(fn2);
  }
  setMeta(data) {
    const updatedMeta = { ...this.getState().meta, ...data };
    const updatedFiles = { ...this.getState().files };
    Object.keys(updatedFiles).forEach((fileID) => {
      updatedFiles[fileID] = {
        ...updatedFiles[fileID],
        meta: { ...updatedFiles[fileID].meta, ...data }
      };
    });
    this.log("Adding metadata:");
    this.log(data);
    this.setState({
      meta: updatedMeta,
      files: updatedFiles
    });
  }
  setFileMeta(fileID, data) {
    const updatedFiles = { ...this.getState().files };
    if (!updatedFiles[fileID]) {
      this.log(`Was trying to set metadata for a file that has been removed: ${fileID}`);
      return;
    }
    const newMeta = { ...updatedFiles[fileID].meta, ...data };
    updatedFiles[fileID] = { ...updatedFiles[fileID], meta: newMeta };
    this.setState({ files: updatedFiles });
  }
  /**
   * Get a file object.
   */
  getFile(fileID) {
    return this.getState().files[fileID];
  }
  /**
   * Get all files in an array.
   */
  getFiles() {
    const { files } = this.getState();
    return Object.values(files);
  }
  getFilesByIds(ids) {
    return ids.map((id) => this.getFile(id));
  }
  getObjectOfFilesPerState() {
    const { files: filesObject, totalProgress, error } = this.getState();
    const files = Object.values(filesObject);
    const inProgressFiles = [];
    const newFiles = [];
    const startedFiles = [];
    const uploadStartedFiles = [];
    const pausedFiles = [];
    const completeFiles = [];
    const erroredFiles = [];
    const inProgressNotPausedFiles = [];
    const processingFiles = [];
    for (const file of files) {
      const { progress } = file;
      if (!progress.uploadComplete && progress.uploadStarted) {
        inProgressFiles.push(file);
        if (!file.isPaused) {
          inProgressNotPausedFiles.push(file);
        }
      }
      if (!progress.uploadStarted) {
        newFiles.push(file);
      }
      if (progress.uploadStarted || progress.preprocess || progress.postprocess) {
        startedFiles.push(file);
      }
      if (progress.uploadStarted) {
        uploadStartedFiles.push(file);
      }
      if (file.isPaused) {
        pausedFiles.push(file);
      }
      if (progress.uploadComplete) {
        completeFiles.push(file);
      }
      if (file.error) {
        erroredFiles.push(file);
      }
      if (progress.preprocess || progress.postprocess) {
        processingFiles.push(file);
      }
    }
    return {
      newFiles,
      startedFiles,
      uploadStartedFiles,
      pausedFiles,
      completeFiles,
      erroredFiles,
      inProgressFiles,
      inProgressNotPausedFiles,
      processingFiles,
      isUploadStarted: uploadStartedFiles.length > 0,
      isAllComplete: totalProgress === 100 && completeFiles.length === files.length && processingFiles.length === 0,
      isAllErrored: !!error && erroredFiles.length === files.length,
      isAllPaused: inProgressFiles.length !== 0 && pausedFiles.length === inProgressFiles.length,
      isUploadInProgress: inProgressFiles.length > 0,
      isSomeGhost: files.some((file) => file.isGhost)
    };
  }
  validateRestrictions(file, files = this.getFiles()) {
    try {
      __privateGet(this, _restricter).validate(files, [file]);
    } catch (err) {
      return err;
    }
    return null;
  }
  validateSingleFile(file) {
    try {
      __privateGet(this, _restricter).validateSingleFile(file);
    } catch (err) {
      return err.message;
    }
    return null;
  }
  validateAggregateRestrictions(files) {
    const existingFiles = this.getFiles();
    try {
      __privateGet(this, _restricter).validateAggregateRestrictions(existingFiles, files);
    } catch (err) {
      return err.message;
    }
    return null;
  }
  checkIfFileAlreadyExists(fileID) {
    const { files } = this.getState();
    if (files[fileID] && !files[fileID].isGhost) {
      return true;
    }
    return false;
  }
  /**
   * Add a new file to `state.files`. This will run `onBeforeFileAdded`,
   * try to guess file type in a clever way, check file against restrictions,
   * and start an upload if `autoProceed === true`.
   */
  addFile(file) {
    __privateMethod(this, _Uppy_instances, assertNewUploadAllowed_fn).call(this, file);
    const { nextFilesState, validFilesToAdd, errors } = __privateMethod(this, _Uppy_instances, checkAndUpdateFileState_fn).call(this, [file]);
    const restrictionErrors = errors.filter((error) => error.isRestriction);
    __privateMethod(this, _Uppy_instances, informAndEmit_fn).call(this, restrictionErrors);
    if (errors.length > 0)
      throw errors[0];
    this.setState({ files: nextFilesState });
    const [firstValidFileToAdd] = validFilesToAdd;
    this.emit("file-added", firstValidFileToAdd);
    this.emit("files-added", validFilesToAdd);
    this.log(`Added file: ${firstValidFileToAdd.name}, ${firstValidFileToAdd.id}, mime type: ${firstValidFileToAdd.type}`);
    __privateMethod(this, _Uppy_instances, startIfAutoProceed_fn).call(this);
    return firstValidFileToAdd.id;
  }
  /**
   * Add multiple files to `state.files`. See the `addFile()` documentation.
   *
   * If an error occurs while adding a file, it is logged and the user is notified.
   * This is good for UI plugins, but not for programmatic use.
   * Programmatic users should usually still use `addFile()` on individual files.
   */
  addFiles(fileDescriptors) {
    __privateMethod(this, _Uppy_instances, assertNewUploadAllowed_fn).call(this);
    const { nextFilesState, validFilesToAdd, errors } = __privateMethod(this, _Uppy_instances, checkAndUpdateFileState_fn).call(this, fileDescriptors);
    const restrictionErrors = errors.filter((error) => error.isRestriction);
    __privateMethod(this, _Uppy_instances, informAndEmit_fn).call(this, restrictionErrors);
    const nonRestrictionErrors = errors.filter((error) => !error.isRestriction);
    if (nonRestrictionErrors.length > 0) {
      let message = "Multiple errors occurred while adding files:\n";
      nonRestrictionErrors.forEach((subError) => {
        message += `
 * ${subError.message}`;
      });
      this.info({
        message: this.i18n("addBulkFilesFailed", {
          smart_count: nonRestrictionErrors.length
        }),
        details: message
      }, "error", this.opts.infoTimeout);
      if (typeof AggregateError === "function") {
        throw new AggregateError(nonRestrictionErrors, message);
      } else {
        const err = new Error(message);
        err.errors = nonRestrictionErrors;
        throw err;
      }
    }
    this.setState({ files: nextFilesState });
    validFilesToAdd.forEach((file) => {
      this.emit("file-added", file);
    });
    this.emit("files-added", validFilesToAdd);
    if (validFilesToAdd.length > 5) {
      this.log(`Added batch of ${validFilesToAdd.length} files`);
    } else {
      Object.values(validFilesToAdd).forEach((file) => {
        this.log(`Added file: ${file.name}
 id: ${file.id}
 type: ${file.type}`);
      });
    }
    if (validFilesToAdd.length > 0) {
      __privateMethod(this, _Uppy_instances, startIfAutoProceed_fn).call(this);
    }
  }
  removeFiles(fileIDs) {
    const { files, currentUploads } = this.getState();
    const updatedFiles = { ...files };
    const updatedUploads = { ...currentUploads };
    const removedFiles = /* @__PURE__ */ Object.create(null);
    fileIDs.forEach((fileID) => {
      if (files[fileID]) {
        removedFiles[fileID] = files[fileID];
        delete updatedFiles[fileID];
      }
    });
    function fileIsNotRemoved(uploadFileID) {
      return removedFiles[uploadFileID] === void 0;
    }
    Object.keys(updatedUploads).forEach((uploadID) => {
      const newFileIDs = currentUploads[uploadID].fileIDs.filter(fileIsNotRemoved);
      if (newFileIDs.length === 0) {
        delete updatedUploads[uploadID];
        return;
      }
      const { capabilities } = this.getState();
      if (newFileIDs.length !== currentUploads[uploadID].fileIDs.length && !capabilities.individualCancellation) {
        throw new Error("The installed uploader plugin does not allow removing files during an upload.");
      }
      updatedUploads[uploadID] = {
        ...currentUploads[uploadID],
        fileIDs: newFileIDs
      };
    });
    const stateUpdate = {
      currentUploads: updatedUploads,
      files: updatedFiles
    };
    if (Object.keys(updatedFiles).length === 0) {
      stateUpdate.allowNewUpload = true;
      stateUpdate.error = null;
      stateUpdate.recoveredState = null;
    }
    this.setState(stateUpdate);
    __privateGet(this, _updateTotalProgressThrottled).call(this);
    const removedFileIDs = Object.keys(removedFiles);
    removedFileIDs.forEach((fileID) => {
      this.emit("file-removed", removedFiles[fileID]);
    });
    if (removedFileIDs.length > 5) {
      this.log(`Removed ${removedFileIDs.length} files`);
    } else {
      this.log(`Removed files: ${removedFileIDs.join(", ")}`);
    }
  }
  removeFile(fileID) {
    this.removeFiles([fileID]);
  }
  pauseResume(fileID) {
    if (!this.getState().capabilities.resumableUploads || this.getFile(fileID).progress.uploadComplete) {
      return void 0;
    }
    const file = this.getFile(fileID);
    const wasPaused = file.isPaused || false;
    const isPaused = !wasPaused;
    this.setFileState(fileID, {
      isPaused
    });
    this.emit("upload-pause", file, isPaused);
    return isPaused;
  }
  pauseAll() {
    const updatedFiles = { ...this.getState().files };
    const inProgressUpdatedFiles = Object.keys(updatedFiles).filter((file) => {
      return !updatedFiles[file].progress.uploadComplete && updatedFiles[file].progress.uploadStarted;
    });
    inProgressUpdatedFiles.forEach((file) => {
      const updatedFile = { ...updatedFiles[file], isPaused: true };
      updatedFiles[file] = updatedFile;
    });
    this.setState({ files: updatedFiles });
    this.emit("pause-all");
  }
  resumeAll() {
    const updatedFiles = { ...this.getState().files };
    const inProgressUpdatedFiles = Object.keys(updatedFiles).filter((file) => {
      return !updatedFiles[file].progress.uploadComplete && updatedFiles[file].progress.uploadStarted;
    });
    inProgressUpdatedFiles.forEach((file) => {
      const updatedFile = {
        ...updatedFiles[file],
        isPaused: false,
        error: null
      };
      updatedFiles[file] = updatedFile;
    });
    this.setState({ files: updatedFiles });
    this.emit("resume-all");
  }
  async retryAll() {
    const result = await __privateMethod(this, _Uppy_instances, doRetryAll_fn).call(this);
    this.emit("complete", result);
    return result;
  }
  cancelAll() {
    this.emit("cancel-all");
    const { files } = this.getState();
    const fileIDs = Object.keys(files);
    if (fileIDs.length) {
      this.removeFiles(fileIDs);
    }
    this.setState(defaultUploadState);
  }
  retryUpload(fileID) {
    this.setFileState(fileID, {
      error: null,
      isPaused: false
    });
    this.emit("upload-retry", this.getFile(fileID));
    const uploadID = __privateMethod(this, _Uppy_instances, createUpload_fn).call(this, [fileID], {
      forceAllowNewUpload: true
      // create new upload even if allowNewUpload: false
    });
    return __privateMethod(this, _Uppy_instances, runUpload_fn).call(this, uploadID);
  }
  logout() {
    this.iteratePlugins((plugin) => {
      ;
      plugin.provider?.logout?.();
    });
  }
  [Symbol.for("uppy test: updateTotalProgress")]() {
    return __privateMethod(this, _Uppy_instances, updateTotalProgress_fn).call(this);
  }
  updateOnlineStatus() {
    const online = window.navigator.onLine ?? true;
    if (!online) {
      this.emit("is-offline");
      this.info(this.i18n("noInternetConnection"), "error", 0);
      this.wasOffline = true;
    } else {
      this.emit("is-online");
      if (this.wasOffline) {
        this.emit("back-online");
        this.info(this.i18n("connectedToInternet"), "success", 3e3);
        this.wasOffline = false;
      }
    }
  }
  getID() {
    return this.opts.id;
  }
  /**
   * Registers a plugin with Core.
   */
  use(Plugin, ...args) {
    if (typeof Plugin !== "function") {
      const msg = `Expected a plugin class, but got ${Plugin === null ? "null" : typeof Plugin}. Please verify that the plugin was imported and spelled correctly.`;
      throw new TypeError(msg);
    }
    const plugin = new Plugin(this, ...args);
    const pluginId = plugin.id;
    if (!pluginId) {
      throw new Error("Your plugin must have an id");
    }
    if (!plugin.type) {
      throw new Error("Your plugin must have a type");
    }
    const existsPluginAlready = this.getPlugin(pluginId);
    if (existsPluginAlready) {
      const msg = `Already found a plugin named '${existsPluginAlready.id}'. Tried to use: '${pluginId}'.
Uppy plugins must have unique \`id\` options.`;
      throw new Error(msg);
    }
    if (Plugin.VERSION) {
      this.log(`Using ${pluginId} v${Plugin.VERSION}`);
    }
    if (plugin.type in __privateGet(this, _plugins)) {
      __privateGet(this, _plugins)[plugin.type].push(plugin);
    } else {
      __privateGet(this, _plugins)[plugin.type] = [plugin];
    }
    plugin.install();
    this.emit("plugin-added", plugin);
    return this;
  }
  /**
   * Find one Plugin by name.
   */
  getPlugin(id) {
    for (const plugins of Object.values(__privateGet(this, _plugins))) {
      const foundPlugin = plugins.find((plugin) => plugin.id === id);
      if (foundPlugin != null)
        return foundPlugin;
    }
    return void 0;
  }
  [Symbol.for("uppy test: getPlugins")](type) {
    return __privateGet(this, _plugins)[type];
  }
  /**
   * Iterate through all `use`d plugins.
   *
   */
  iteratePlugins(method) {
    Object.values(__privateGet(this, _plugins)).flat(1).forEach(method);
  }
  /**
   * Uninstall and remove a plugin.
   *
   * @param {object} instance The plugin instance to remove.
   */
  removePlugin(instance) {
    this.log(`Removing plugin ${instance.id}`);
    this.emit("plugin-remove", instance);
    if (instance.uninstall) {
      instance.uninstall();
    }
    const list = __privateGet(this, _plugins)[instance.type];
    const index = list.findIndex((item) => item.id === instance.id);
    if (index !== -1) {
      list.splice(index, 1);
    }
    const state = this.getState();
    const updatedState = {
      plugins: {
        ...state.plugins,
        [instance.id]: void 0
      }
    };
    this.setState(updatedState);
  }
  /**
   * Uninstall all plugins and close down this Uppy instance.
   */
  destroy() {
    this.log(`Closing Uppy instance ${this.opts.id}: removing all files and uninstalling plugins`);
    this.cancelAll();
    __privateGet(this, _storeUnsubscribe).call(this);
    this.iteratePlugins((plugin) => {
      this.removePlugin(plugin);
    });
    if (typeof window !== "undefined" && window.removeEventListener) {
      window.removeEventListener("online", __privateGet(this, _updateOnlineStatus));
      window.removeEventListener("offline", __privateGet(this, _updateOnlineStatus));
    }
  }
  hideInfo() {
    const { info } = this.getState();
    this.setState({ info: info.slice(1) });
    this.emit("info-hidden");
  }
  /**
   * Set info message in `state.info`, so that UI plugins like `Informer`
   * can display the message.
   */
  info(message, type = "info", duration2 = 3e3) {
    const isComplexMessage = typeof message === "object";
    this.setState({
      info: [
        ...this.getState().info,
        {
          type,
          message: isComplexMessage ? message.message : message,
          details: isComplexMessage ? message.details : null
        }
      ]
    });
    setTimeout(() => this.hideInfo(), duration2);
    this.emit("info-visible");
  }
  /**
   * Passes messages to a function, provided in `opts.logger`.
   * If `opts.logger: Uppy.debugLogger` or `opts.debug: true`, logs to the browser console.
   */
  log(message, type) {
    const { logger } = this.opts;
    switch (type) {
      case "error":
        logger.error(message);
        break;
      case "warning":
        logger.warn(message);
        break;
      default:
        logger.debug(message);
        break;
    }
  }
  registerRequestClient(id, client) {
    __privateGet(this, _requestClientById).set(id, client);
  }
  /** @protected */
  getRequestClientForFile(file) {
    if (!file.remote)
      throw new Error(`Tried to get RequestClient for a non-remote file ${file.id}`);
    const requestClient = __privateGet(this, _requestClientById).get(file.remote.requestClientId);
    if (requestClient == null)
      throw new Error(`requestClientId "${file.remote.requestClientId}" not registered for file "${file.id}"`);
    return requestClient;
  }
  /**
   * Restore an upload by its ID.
   */
  restore(uploadID) {
    this.log(`Core: attempting to restore upload "${uploadID}"`);
    if (!this.getState().currentUploads[uploadID]) {
      __privateMethod(this, _Uppy_instances, removeUpload_fn).call(this, uploadID);
      return Promise.reject(new Error("Nonexistent upload"));
    }
    return __privateMethod(this, _Uppy_instances, runUpload_fn).call(this, uploadID);
  }
  [Symbol.for("uppy test: createUpload")](...args) {
    return __privateMethod(this, _Uppy_instances, createUpload_fn).call(this, ...args);
  }
  /**
   * Add data to an upload's result object.
   */
  addResultData(uploadID, data) {
    if (!__privateMethod(this, _Uppy_instances, getUpload_fn).call(this, uploadID)) {
      this.log(`Not setting result for an upload that has been removed: ${uploadID}`);
      return;
    }
    const { currentUploads } = this.getState();
    const currentUpload = {
      ...currentUploads[uploadID],
      result: { ...currentUploads[uploadID].result, ...data }
    };
    this.setState({
      currentUploads: { ...currentUploads, [uploadID]: currentUpload }
    });
  }
  /**
   * Start an upload for all the files that are not currently being uploaded.
   */
  async upload() {
    if (!__privateGet(this, _plugins).uploader?.length) {
      this.log("No uploader type plugins are used", "warning");
    }
    let { files } = this.getState();
    const filesToRetry = __privateMethod(this, _Uppy_instances, getFilesToRetry_fn).call(this);
    if (filesToRetry.length > 0) {
      const retryResult = await __privateMethod(this, _Uppy_instances, doRetryAll_fn).call(this);
      const hasNewFiles = this.getFiles().filter((file) => file.progress.uploadStarted == null).length > 0;
      if (!hasNewFiles) {
        this.emit("complete", retryResult);
        return retryResult;
      }
      ;
      ({ files } = this.getState());
    }
    const onBeforeUploadResult = this.opts.onBeforeUpload(files);
    if (onBeforeUploadResult === false) {
      return Promise.reject(new Error("Not starting the upload because onBeforeUpload returned false"));
    }
    if (onBeforeUploadResult && typeof onBeforeUploadResult === "object") {
      files = onBeforeUploadResult;
      this.setState({
        files
      });
    }
    return Promise.resolve().then(() => __privateGet(this, _restricter).validateMinNumberOfFiles(files)).catch((err) => {
      __privateMethod(this, _Uppy_instances, informAndEmit_fn).call(this, [err]);
      throw err;
    }).then(() => {
      if (!__privateMethod(this, _Uppy_instances, checkRequiredMetaFields_fn).call(this, files)) {
        throw new RestrictionError(this.i18n("missingRequiredMetaField"));
      }
    }).catch((err) => {
      throw err;
    }).then(async () => {
      const { currentUploads } = this.getState();
      const currentlyUploadingFiles = Object.values(currentUploads).flatMap((curr) => curr.fileIDs);
      const waitingFileIDs = [];
      Object.keys(files).forEach((fileID) => {
        const file = this.getFile(fileID);
        if (!file.progress.uploadStarted && currentlyUploadingFiles.indexOf(fileID) === -1) {
          waitingFileIDs.push(file.id);
        }
      });
      const uploadID = __privateMethod(this, _Uppy_instances, createUpload_fn).call(this, waitingFileIDs);
      const result = await __privateMethod(this, _Uppy_instances, runUpload_fn).call(this, uploadID);
      this.emit("complete", result);
      return result;
    }).catch((err) => {
      this.emit("error", err);
      this.log(err, "error");
      throw err;
    });
  }
};
_plugins = new WeakMap();
_restricter = new WeakMap();
_storeUnsubscribe = new WeakMap();
_emitter = new WeakMap();
_preProcessors = new WeakMap();
_uploaders = new WeakMap();
_postProcessors = new WeakMap();
_Uppy_instances = new WeakSet();
informAndEmit_fn = function(errors) {
  for (const error of errors) {
    if (error.isRestriction) {
      this.emit("restriction-failed", error.file, error);
    } else {
      this.emit("error", error, error.file);
    }
    this.log(error, "warning");
  }
  const userFacingErrors = errors.filter((error) => error.isUserFacing);
  const maxNumToShow = 4;
  const firstErrors = userFacingErrors.slice(0, maxNumToShow);
  const additionalErrors = userFacingErrors.slice(maxNumToShow);
  firstErrors.forEach(({ message, details = "" }) => {
    this.info({ message, details }, "error", this.opts.infoTimeout);
  });
  if (additionalErrors.length > 0) {
    this.info({
      message: this.i18n("additionalRestrictionsFailed", {
        count: additionalErrors.length
      })
    });
  }
};
checkRequiredMetaFieldsOnFile_fn = function(file) {
  const { missingFields, error } = __privateGet(this, _restricter).getMissingRequiredMetaFields(file);
  if (missingFields.length > 0) {
    this.setFileState(file.id, {
      missingRequiredMetaFields: missingFields,
      error: error.message
    });
    this.log(error.message);
    this.emit("restriction-failed", file, error);
    return false;
  }
  if (missingFields.length === 0 && file.missingRequiredMetaFields) {
    this.setFileState(file.id, {
      missingRequiredMetaFields: []
    });
  }
  return true;
};
checkRequiredMetaFields_fn = function(files) {
  let success = true;
  for (const file of Object.values(files)) {
    if (!__privateMethod(this, _Uppy_instances, checkRequiredMetaFieldsOnFile_fn).call(this, file)) {
      success = false;
    }
  }
  return success;
};
assertNewUploadAllowed_fn = function(file) {
  const { allowNewUpload } = this.getState();
  if (allowNewUpload === false) {
    const error = new RestrictionError(this.i18n("noMoreFilesAllowed"), {
      file
    });
    __privateMethod(this, _Uppy_instances, informAndEmit_fn).call(this, [error]);
    throw error;
  }
};
/**
 * Create a file state object based on user-provided `addFile()` options.
 */
transformFile_fn = function(fileDescriptorOrFile) {
  const file = fileDescriptorOrFile instanceof File ? {
    name: fileDescriptorOrFile.name,
    type: fileDescriptorOrFile.type,
    size: fileDescriptorOrFile.size,
    data: fileDescriptorOrFile
  } : fileDescriptorOrFile;
  const fileType = getFileType(file);
  const fileName = getFileName(fileType, file);
  const fileExtension = getFileNameAndExtension(fileName).extension;
  const id = getSafeFileId(file, this.getID());
  const meta = file.meta || {};
  meta.name = fileName;
  meta.type = fileType;
  const size = Number.isFinite(file.data.size) ? file.data.size : null;
  return {
    source: file.source || "",
    id,
    name: fileName,
    extension: fileExtension || "",
    meta: {
      ...this.getState().meta,
      ...meta
    },
    type: fileType,
    data: file.data,
    progress: {
      percentage: 0,
      bytesUploaded: false,
      bytesTotal: size,
      uploadComplete: false,
      uploadStarted: null
    },
    size,
    isGhost: false,
    isRemote: file.isRemote || false,
    remote: file.remote,
    preview: file.preview
  };
};
// Schedule an upload if `autoProceed` is enabled.
startIfAutoProceed_fn = function() {
  if (this.opts.autoProceed && !this.scheduledAutoProceed) {
    this.scheduledAutoProceed = setTimeout(() => {
      this.scheduledAutoProceed = null;
      this.upload().catch((err) => {
        if (!err.isRestriction) {
          this.log(err.stack || err.message || err);
        }
      });
    }, 4);
  }
};
checkAndUpdateFileState_fn = function(filesToAdd) {
  let { files: existingFiles } = this.getState();
  let nextFilesState = { ...existingFiles };
  const validFilesToAdd = [];
  const errors = [];
  for (const fileToAdd of filesToAdd) {
    try {
      let newFile = __privateMethod(this, _Uppy_instances, transformFile_fn).call(this, fileToAdd);
      const isGhost = existingFiles[newFile.id]?.isGhost;
      if (isGhost) {
        const existingFileState = existingFiles[newFile.id];
        newFile = {
          ...existingFileState,
          isGhost: false,
          data: fileToAdd.data
        };
        this.log(`Replaced the blob in the restored ghost file: ${newFile.name}, ${newFile.id}`);
      }
      const onBeforeFileAddedResult = this.opts.onBeforeFileAdded(newFile, nextFilesState);
      existingFiles = this.getState().files;
      nextFilesState = { ...existingFiles, ...nextFilesState };
      if (!onBeforeFileAddedResult && this.checkIfFileAlreadyExists(newFile.id)) {
        throw new RestrictionError(this.i18n("noDuplicates", {
          fileName: newFile.name ?? this.i18n("unnamed")
        }), { file: fileToAdd });
      }
      if (onBeforeFileAddedResult === false && !isGhost) {
        throw new RestrictionError("Cannot add the file because onBeforeFileAdded returned false.", { isUserFacing: false, file: fileToAdd });
      } else if (typeof onBeforeFileAddedResult === "object" && onBeforeFileAddedResult !== null) {
        newFile = onBeforeFileAddedResult;
      }
      __privateGet(this, _restricter).validateSingleFile(newFile);
      nextFilesState[newFile.id] = newFile;
      validFilesToAdd.push(newFile);
    } catch (err) {
      errors.push(err);
    }
  }
  try {
    __privateGet(this, _restricter).validateAggregateRestrictions(Object.values(existingFiles), validFilesToAdd);
  } catch (err) {
    errors.push(err);
    return {
      nextFilesState: existingFiles,
      validFilesToAdd: [],
      errors
    };
  }
  return {
    nextFilesState,
    validFilesToAdd,
    errors
  };
};
getFilesToRetry_fn = function() {
  const { files } = this.getState();
  return Object.keys(files).filter((fileId) => {
    const file = files[fileId];
    return file.error && (!file.missingRequiredMetaFields || file.missingRequiredMetaFields.length === 0);
  });
};
doRetryAll_fn = async function() {
  const filesToRetry = __privateMethod(this, _Uppy_instances, getFilesToRetry_fn).call(this);
  const updatedFiles = { ...this.getState().files };
  filesToRetry.forEach((fileID) => {
    updatedFiles[fileID] = {
      ...updatedFiles[fileID],
      isPaused: false,
      error: null
    };
  });
  this.setState({
    files: updatedFiles,
    error: null
  });
  this.emit("retry-all", this.getFilesByIds(filesToRetry));
  if (filesToRetry.length === 0) {
    return {
      successful: [],
      failed: []
    };
  }
  const uploadID = __privateMethod(this, _Uppy_instances, createUpload_fn).call(this, filesToRetry, {
    forceAllowNewUpload: true
    // create new upload even if allowNewUpload: false
  });
  return __privateMethod(this, _Uppy_instances, runUpload_fn).call(this, uploadID);
};
_handleUploadProgress = new WeakMap();
updateTotalProgress_fn = function() {
  const totalProgress = __privateMethod(this, _Uppy_instances, calculateTotalProgress_fn).call(this);
  let totalProgressPercent = null;
  if (totalProgress != null) {
    totalProgressPercent = Math.round(totalProgress * 100);
    if (totalProgressPercent > 100)
      totalProgressPercent = 100;
    else if (totalProgressPercent < 0)
      totalProgressPercent = 0;
  }
  this.emit("progress", totalProgressPercent ?? 0);
  this.setState({
    totalProgress: totalProgressPercent ?? 0
  });
};
_updateTotalProgressThrottled = new WeakMap();
calculateTotalProgress_fn = function() {
  const files = this.getFiles();
  const filesInProgress = files.filter((file) => {
    return file.progress.uploadStarted || file.progress.preprocess || file.progress.postprocess;
  });
  if (filesInProgress.length === 0) {
    return 0;
  }
  if (filesInProgress.every((file) => file.progress.uploadComplete)) {
    return 1;
  }
  const isSizedFile = (file) => file.progress.bytesTotal != null && file.progress.bytesTotal !== 0;
  const sizedFilesInProgress = filesInProgress.filter(isSizedFile);
  const unsizedFilesInProgress = filesInProgress.filter((file) => !isSizedFile(file));
  if (sizedFilesInProgress.every((file) => file.progress.uploadComplete) && unsizedFilesInProgress.length > 0 && !unsizedFilesInProgress.every((file) => file.progress.uploadComplete)) {
    return null;
  }
  const totalFilesSize = sizedFilesInProgress.reduce((acc, file) => acc + (file.progress.bytesTotal ?? 0), 0);
  const totalUploadedSize = sizedFilesInProgress.reduce((acc, file) => acc + (file.progress.bytesUploaded || 0), 0);
  return totalFilesSize === 0 ? 0 : totalUploadedSize / totalFilesSize;
};
/**
 * Registers listeners for all global actions, like:
 * `error`, `file-removed`, `upload-progress`
 */
addListeners_fn = function() {
  const errorHandler = (error, file, response) => {
    let errorMsg = error.message || "Unknown error";
    if (error.details) {
      errorMsg += ` ${error.details}`;
    }
    this.setState({ error: errorMsg });
    if (file != null && file.id in this.getState().files) {
      this.setFileState(file.id, {
        error: errorMsg,
        response
      });
    }
  };
  this.on("error", errorHandler);
  this.on("upload-error", (file, error, response) => {
    errorHandler(error, file, response);
    if (typeof error === "object" && error.message) {
      this.log(error.message, "error");
      const newError = new Error(this.i18n("failedToUpload", { file: file?.name ?? "" }));
      newError.isUserFacing = true;
      newError.details = error.message;
      if (error.details) {
        newError.details += ` ${error.details}`;
      }
      __privateMethod(this, _Uppy_instances, informAndEmit_fn).call(this, [newError]);
    } else {
      __privateMethod(this, _Uppy_instances, informAndEmit_fn).call(this, [error]);
    }
  });
  let uploadStalledWarningRecentlyEmitted = null;
  this.on("upload-stalled", (error, files) => {
    const { message } = error;
    const details = files.map((file) => file.meta.name).join(", ");
    if (!uploadStalledWarningRecentlyEmitted) {
      this.info({ message, details }, "warning", this.opts.infoTimeout);
      uploadStalledWarningRecentlyEmitted = setTimeout(() => {
        uploadStalledWarningRecentlyEmitted = null;
      }, this.opts.infoTimeout);
    }
    this.log(`${message} ${details}`.trim(), "warning");
  });
  this.on("upload", () => {
    this.setState({ error: null });
  });
  const onUploadStarted = (files) => {
    const filesFiltered = files.filter((file) => {
      const exists = file != null && this.getFile(file.id);
      if (!exists)
        this.log(`Not setting progress for a file that has been removed: ${file?.id}`);
      return exists;
    });
    const filesState = Object.fromEntries(filesFiltered.map((file) => [
      file.id,
      {
        progress: {
          uploadStarted: Date.now(),
          uploadComplete: false,
          bytesUploaded: 0,
          bytesTotal: file.size
        }
      }
    ]));
    this.patchFilesState(filesState);
  };
  this.on("upload-start", onUploadStarted);
  this.on("upload-progress", __privateGet(this, _handleUploadProgress));
  this.on("upload-success", (file, uploadResp) => {
    if (file == null || !this.getFile(file.id)) {
      this.log(`Not setting progress for a file that has been removed: ${file?.id}`);
      return;
    }
    const currentProgress = this.getFile(file.id).progress;
    this.setFileState(file.id, {
      progress: {
        ...currentProgress,
        postprocess: __privateGet(this, _postProcessors).size > 0 ? {
          mode: "indeterminate"
        } : void 0,
        uploadComplete: true,
        percentage: 100,
        bytesUploaded: currentProgress.bytesTotal
      },
      response: uploadResp,
      uploadURL: uploadResp.uploadURL,
      isPaused: false
    });
    if (file.size == null) {
      this.setFileState(file.id, {
        size: uploadResp.bytesUploaded || currentProgress.bytesTotal
      });
    }
    __privateGet(this, _updateTotalProgressThrottled).call(this);
  });
  this.on("preprocess-progress", (file, progress) => {
    if (file == null || !this.getFile(file.id)) {
      this.log(`Not setting progress for a file that has been removed: ${file?.id}`);
      return;
    }
    this.setFileState(file.id, {
      progress: { ...this.getFile(file.id).progress, preprocess: progress }
    });
  });
  this.on("preprocess-complete", (file) => {
    if (file == null || !this.getFile(file.id)) {
      this.log(`Not setting progress for a file that has been removed: ${file?.id}`);
      return;
    }
    const files = { ...this.getState().files };
    files[file.id] = {
      ...files[file.id],
      progress: { ...files[file.id].progress }
    };
    delete files[file.id].progress.preprocess;
    this.setState({ files });
  });
  this.on("postprocess-progress", (file, progress) => {
    if (file == null || !this.getFile(file.id)) {
      this.log(`Not setting progress for a file that has been removed: ${file?.id}`);
      return;
    }
    this.setFileState(file.id, {
      progress: {
        ...this.getState().files[file.id].progress,
        postprocess: progress
      }
    });
  });
  this.on("postprocess-complete", (file) => {
    if (file == null || !this.getFile(file.id)) {
      this.log(`Not setting progress for a file that has been removed: ${file?.id}`);
      return;
    }
    const files = {
      ...this.getState().files
    };
    files[file.id] = {
      ...files[file.id],
      progress: {
        ...files[file.id].progress
      }
    };
    delete files[file.id].progress.postprocess;
    this.setState({ files });
  });
  this.on("restored", () => {
    __privateGet(this, _updateTotalProgressThrottled).call(this);
  });
  this.on("dashboard:file-edit-complete", (file) => {
    if (file) {
      __privateMethod(this, _Uppy_instances, checkRequiredMetaFieldsOnFile_fn).call(this, file);
    }
  });
  if (typeof window !== "undefined" && window.addEventListener) {
    window.addEventListener("online", __privateGet(this, _updateOnlineStatus));
    window.addEventListener("offline", __privateGet(this, _updateOnlineStatus));
    setTimeout(__privateGet(this, _updateOnlineStatus), 3e3);
  }
};
_updateOnlineStatus = new WeakMap();
_requestClientById = new WeakMap();
/**
 * Create an upload for a bunch of files.
 *
 */
createUpload_fn = function(fileIDs, opts = {}) {
  const { forceAllowNewUpload = false } = opts;
  const { allowNewUpload, currentUploads } = this.getState();
  if (!allowNewUpload && !forceAllowNewUpload) {
    throw new Error("Cannot create a new upload: already uploading.");
  }
  const uploadID = nanoid();
  this.emit("upload", uploadID, this.getFilesByIds(fileIDs));
  this.setState({
    allowNewUpload: this.opts.allowMultipleUploadBatches !== false && this.opts.allowMultipleUploads !== false,
    currentUploads: {
      ...currentUploads,
      [uploadID]: {
        fileIDs,
        step: 0,
        result: {}
      }
    }
  });
  return uploadID;
};
getUpload_fn = function(uploadID) {
  const { currentUploads } = this.getState();
  return currentUploads[uploadID];
};
/**
 * Remove an upload, eg. if it has been canceled or completed.
 *
 */
removeUpload_fn = function(uploadID) {
  const currentUploads = { ...this.getState().currentUploads };
  delete currentUploads[uploadID];
  this.setState({
    currentUploads
  });
};
runUpload_fn = async function(uploadID) {
  const getCurrentUpload = () => {
    const { currentUploads } = this.getState();
    return currentUploads[uploadID];
  };
  let currentUpload = getCurrentUpload();
  const steps = [
    ...__privateGet(this, _preProcessors),
    ...__privateGet(this, _uploaders),
    ...__privateGet(this, _postProcessors)
  ];
  try {
    for (let step = currentUpload.step || 0; step < steps.length; step++) {
      if (!currentUpload) {
        break;
      }
      const fn2 = steps[step];
      this.setState({
        currentUploads: {
          ...this.getState().currentUploads,
          [uploadID]: {
            ...currentUpload,
            step
          }
        }
      });
      const { fileIDs } = currentUpload;
      await fn2(fileIDs, uploadID);
      currentUpload = getCurrentUpload();
    }
  } catch (err) {
    __privateMethod(this, _Uppy_instances, removeUpload_fn).call(this, uploadID);
    throw err;
  }
  if (currentUpload) {
    currentUpload.fileIDs.forEach((fileID) => {
      const file = this.getFile(fileID);
      if (file?.progress.postprocess) {
        this.emit("postprocess-complete", file);
      }
    });
    const files = currentUpload.fileIDs.map((fileID) => this.getFile(fileID));
    const successful = files.filter((file) => !file.error);
    const failed = files.filter((file) => file.error);
    this.addResultData(uploadID, { successful, failed, uploadID });
    currentUpload = getCurrentUpload();
  }
  let result;
  if (currentUpload) {
    result = currentUpload.result;
    __privateMethod(this, _Uppy_instances, removeUpload_fn).call(this, uploadID);
  }
  if (result == null) {
    this.log(`Not setting result for an upload that has been removed: ${uploadID}`);
    result = {
      successful: [],
      failed: [],
      uploadID
    };
  }
  return result;
};
__publicField(_Uppy, "VERSION", package_default2.version);
var Uppy = _Uppy;
var Uppy_default = Uppy;

// node_modules/preact/jsx-runtime/dist/jsxRuntime.module.js
var f3 = 0;
function u3(e4, t4, n3, o4, i4, u5) {
  t4 || (t4 = {});
  var a4, c4, p4 = t4;
  if ("ref" in p4) for (c4 in p4 = {}, t4) "ref" == c4 ? a4 = t4[c4] : p4[c4] = t4[c4];
  var l4 = { type: e4, props: p4, key: n3, ref: a4, __k: null, __: null, __b: 0, __e: null, __c: null, constructor: void 0, __v: --f3, __i: -1, __u: 0, __source: i4, __self: u5 };
  if ("function" == typeof e4 && (a4 = e4.defaultProps)) for (c4 in a4) void 0 === p4[c4] && (p4[c4] = a4[c4]);
  return l.vnode && l.vnode(l4), l4;
}

// node_modules/@uppy/informer/package.json
var package_default3 = {
  name: "@uppy/informer",
  description: "A notification and error pop-up bar for Uppy.",
  version: "4.3.2",
  license: "MIT",
  main: "lib/index.js",
  style: "dist/style.min.css",
  type: "module",
  scripts: {
    build: "tsc --build tsconfig.build.json",
    "build:css": "sass --load-path=../../ src/style.scss dist/style.css && postcss dist/style.css -u cssnano -o dist/style.min.css",
    typecheck: "tsc --build"
  },
  keywords: [
    "file uploader",
    "uppy",
    "uppy-plugin",
    "notification",
    "bar",
    "ui"
  ],
  homepage: "https://uppy.io",
  bugs: {
    url: "https://github.com/transloadit/uppy/issues"
  },
  repository: {
    type: "git",
    url: "git+https://github.com/transloadit/uppy.git"
  },
  files: [
    "src",
    "lib",
    "dist",
    "CHANGELOG.md"
  ],
  dependencies: {
    "@uppy/utils": "^6.2.2",
    preact: "^10.5.13"
  },
  peerDependencies: {
    "@uppy/core": "^4.5.2"
  },
  devDependencies: {
    cssnano: "^7.0.7",
    postcss: "^8.5.6",
    "postcss-cli": "^11.0.1",
    sass: "^1.89.2",
    typescript: "^5.8.3"
  }
};

// node_modules/@uppy/informer/lib/FadeIn.js
var TRANSITION_MS = 300;
var FadeIn = class extends C {
  constructor() {
    super(...arguments);
    __publicField(this, "ref", M());
  }
  componentWillEnter(callback) {
    this.ref.current.style.opacity = "1";
    this.ref.current.style.transform = "none";
    setTimeout(callback, TRANSITION_MS);
  }
  componentWillLeave(callback) {
    this.ref.current.style.opacity = "0";
    this.ref.current.style.transform = "translateY(350%)";
    setTimeout(callback, TRANSITION_MS);
  }
  render() {
    const { children } = this.props;
    return u3("div", { className: "uppy-Informer-animated", ref: this.ref, children });
  }
};

// node_modules/@uppy/informer/lib/TransitionGroup.js
function assign(obj, props) {
  return Object.assign(obj, props);
}
function getKey(vnode, fallback) {
  return vnode?.key ?? fallback;
}
function linkRef(component, name) {
  const cache = component._ptgLinkedRefs || (component._ptgLinkedRefs = {});
  return cache[name] || // biome-ignore lint/suspicious/noAssignInExpressions: ...
  (cache[name] = (c4) => {
    component.refs[name] = c4;
  });
}
function getChildMapping(children) {
  const out = {};
  for (let i4 = 0; i4 < children.length; i4++) {
    if (children[i4] != null) {
      const key = getKey(children[i4], i4.toString(36));
      out[key] = children[i4];
    }
  }
  return out;
}
function mergeChildMappings(prev, next) {
  prev = prev || {};
  next = next || {};
  const getValueForKey = (key) => Object.hasOwn(next, key) ? next[key] : prev[key];
  const nextKeysPending = {};
  let pendingKeys = [];
  for (const prevKey in prev) {
    if (Object.hasOwn(next, prevKey)) {
      if (pendingKeys.length) {
        nextKeysPending[prevKey] = pendingKeys;
        pendingKeys = [];
      }
    } else {
      pendingKeys.push(prevKey);
    }
  }
  const childMapping = {};
  for (const nextKey in next) {
    if (Object.hasOwn(nextKeysPending, nextKey)) {
      for (let i4 = 0; i4 < nextKeysPending[nextKey].length; i4++) {
        const pendingNextKey = nextKeysPending[nextKey][i4];
        childMapping[nextKeysPending[nextKey][i4]] = getValueForKey(pendingNextKey);
      }
    }
    childMapping[nextKey] = getValueForKey(nextKey);
  }
  for (let i4 = 0; i4 < pendingKeys.length; i4++) {
    childMapping[pendingKeys[i4]] = getValueForKey(pendingKeys[i4]);
  }
  return childMapping;
}
var identity = (i4) => i4;
var TransitionGroup = class extends C {
  constructor(props, context) {
    super(props, context);
    this.refs = {};
    this.state = {
      children: getChildMapping(F(F(this.props.children)) || [])
    };
    this.performAppear = this.performAppear.bind(this);
    this.performEnter = this.performEnter.bind(this);
    this.performLeave = this.performLeave.bind(this);
  }
  componentWillMount() {
    this.currentlyTransitioningKeys = {};
    this.keysToAbortLeave = [];
    this.keysToEnter = [];
    this.keysToLeave = [];
  }
  componentDidMount() {
    const initialChildMapping = this.state.children;
    for (const key in initialChildMapping) {
      if (initialChildMapping[key]) {
        this.performAppear(key);
      }
    }
  }
  componentWillReceiveProps(nextProps) {
    const nextChildMapping = getChildMapping(F(nextProps.children) || []);
    const prevChildMapping = this.state.children;
    this.setState((prevState) => ({
      children: mergeChildMappings(prevState.children, nextChildMapping)
    }));
    let key;
    for (key in nextChildMapping) {
      if (Object.hasOwn(nextChildMapping, key)) {
        const hasPrev = prevChildMapping && Object.hasOwn(prevChildMapping, key);
        if (nextChildMapping[key] && hasPrev && this.currentlyTransitioningKeys[key]) {
          this.keysToEnter.push(key);
          this.keysToAbortLeave.push(key);
        } else if (nextChildMapping[key] && !hasPrev && !this.currentlyTransitioningKeys[key]) {
          this.keysToEnter.push(key);
        }
      }
    }
    for (key in prevChildMapping) {
      if (Object.hasOwn(prevChildMapping, key)) {
        const hasNext = nextChildMapping && Object.hasOwn(nextChildMapping, key);
        if (prevChildMapping[key] && !hasNext && !this.currentlyTransitioningKeys[key]) {
          this.keysToLeave.push(key);
        }
      }
    }
  }
  componentDidUpdate() {
    const { keysToEnter } = this;
    this.keysToEnter = [];
    keysToEnter.forEach(this.performEnter);
    const { keysToLeave } = this;
    this.keysToLeave = [];
    keysToLeave.forEach(this.performLeave);
  }
  _finishAbort(key) {
    const idx = this.keysToAbortLeave.indexOf(key);
    if (idx !== -1) {
      this.keysToAbortLeave.splice(idx, 1);
    }
  }
  performAppear(key) {
    this.currentlyTransitioningKeys[key] = true;
    const component = this.refs[key];
    if (component?.componentWillAppear) {
      component.componentWillAppear(this._handleDoneAppearing.bind(this, key));
    } else {
      this._handleDoneAppearing(key);
    }
  }
  _handleDoneAppearing(key) {
    const component = this.refs[key];
    if (component?.componentDidAppear) {
      component.componentDidAppear();
    }
    delete this.currentlyTransitioningKeys[key];
    this._finishAbort(key);
    const currentChildMapping = getChildMapping(F(this.props.children) || []);
    if (!currentChildMapping || !Object.hasOwn(currentChildMapping, key)) {
      this.performLeave(key);
    }
  }
  performEnter(key) {
    this.currentlyTransitioningKeys[key] = true;
    const component = this.refs[key];
    if (component?.componentWillEnter) {
      component.componentWillEnter(this._handleDoneEntering.bind(this, key));
    } else {
      this._handleDoneEntering(key);
    }
  }
  _handleDoneEntering(key) {
    const component = this.refs[key];
    if (component?.componentDidEnter) {
      component.componentDidEnter();
    }
    delete this.currentlyTransitioningKeys[key];
    this._finishAbort(key);
    const currentChildMapping = getChildMapping(F(this.props.children) || []);
    if (!currentChildMapping || !Object.hasOwn(currentChildMapping, key)) {
      this.performLeave(key);
    }
  }
  performLeave(key) {
    const idx = this.keysToAbortLeave.indexOf(key);
    if (idx !== -1) {
      return;
    }
    this.currentlyTransitioningKeys[key] = true;
    const component = this.refs[key];
    if (component?.componentWillLeave) {
      component.componentWillLeave(this._handleDoneLeaving.bind(this, key));
    } else {
      this._handleDoneLeaving(key);
    }
  }
  _handleDoneLeaving(key) {
    const idx = this.keysToAbortLeave.indexOf(key);
    if (idx !== -1) {
      return;
    }
    const component = this.refs[key];
    if (component?.componentDidLeave) {
      component.componentDidLeave();
    }
    delete this.currentlyTransitioningKeys[key];
    const currentChildMapping = getChildMapping(F(this.props.children) || []);
    if (currentChildMapping && Object.hasOwn(currentChildMapping, key)) {
      this.performEnter(key);
    } else {
      const children = assign({}, this.state.children);
      delete children[key];
      this.setState({ children });
    }
  }
  render({ childFactory, transitionLeave, transitionName: transitionName2, transitionAppear, transitionEnter, transitionLeaveTimeout, transitionEnterTimeout, transitionAppearTimeout, component, ...props }, { children }) {
    const childrenToRender = Object.entries(children).map(([key, child]) => {
      if (!child)
        return void 0;
      const ref = linkRef(this, key);
      return W(childFactory(child), { ref, key });
    }).filter(Boolean);
    return k(component, props, childrenToRender);
  }
};
TransitionGroup.defaultProps = {
  component: "span",
  childFactory: identity
};
var TransitionGroup_default = TransitionGroup;

// node_modules/@uppy/informer/lib/Informer.js
var Informer = class extends UIPlugin_default {
  constructor(uppy, opts) {
    super(uppy, opts);
    __publicField(this, "render", (state) => {
      return u3("div", { className: "uppy uppy-Informer", children: u3(TransitionGroup_default, { children: state.info.map((info) => u3(FadeIn, { children: u3("p", { role: "alert", children: [info.message, " ", info.details && // biome-ignore lint/a11y/useKeyWithClickEvents: ...
      u3("span", { "aria-label": info.details, "data-microtip-position": "top-left", "data-microtip-size": "medium", role: "tooltip", onClick: () => alert(`${info.message} 

 ${info.details}`), children: "?" })] }) }, info.message)) }) });
    });
    this.type = "progressindicator";
    this.id = this.opts.id || "Informer";
    this.title = "Informer";
  }
  install() {
    const { target } = this.opts;
    if (target) {
      this.mount(target, this);
    }
  }
};
__publicField(Informer, "VERSION", package_default3.version);

// node_modules/@uppy/provider-views/lib/ProviderView/AuthView.js
function GoogleIcon() {
  return u3("svg", { width: "26", height: "26", viewBox: "0 0 26 26", xmlns: "http://www.w3.org/2000/svg", children: u3("g", { fill: "none", "fill-rule": "evenodd", children: [u3("circle", { fill: "#FFF", cx: "13", cy: "13", r: "13" }), u3("path", { d: "M21.64 13.205c0-.639-.057-1.252-.164-1.841H13v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z", fill: "#4285F4", "fill-rule": "nonzero" }), u3("path", { d: "M13 22c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H4.957v2.332A8.997 8.997 0 0013 22z", fill: "#34A853", "fill-rule": "nonzero" }), u3("path", { d: "M7.964 14.71A5.41 5.41 0 017.682 13c0-.593.102-1.17.282-1.71V8.958H4.957A8.996 8.996 0 004 13c0 1.452.348 2.827.957 4.042l3.007-2.332z", fill: "#FBBC05", "fill-rule": "nonzero" }), u3("path", { d: "M13 7.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C17.463 4.891 15.426 4 13 4a8.997 8.997 0 00-8.043 4.958l3.007 2.332C8.672 9.163 10.656 7.58 13 7.58z", fill: "#EA4335", "fill-rule": "nonzero" }), u3("path", { d: "M4 4h18v18H4z" })] }) });
}
function DefaultForm({ pluginName, i18n, onAuth }) {
  const isGoogleDrive = pluginName === "Google Drive";
  const onSubmit = q2((e4) => {
    e4.preventDefault();
    onAuth();
  }, [onAuth]);
  return u3("form", { onSubmit, children: isGoogleDrive ? u3("button", { type: "submit", className: "uppy-u-reset uppy-c-btn uppy-c-btn-primary uppy-Provider-authBtn uppy-Provider-btn-google", "data-uppy-super-focusable": true, children: [u3(GoogleIcon, {}), i18n("signInWithGoogle")] }) : u3("button", { type: "submit", className: "uppy-u-reset uppy-c-btn uppy-c-btn-primary uppy-Provider-authBtn", "data-uppy-super-focusable": true, children: i18n("authenticateWith", { pluginName }) }) });
}
var defaultRenderForm = ({ pluginName, i18n, onAuth }) => u3(DefaultForm, { pluginName, i18n, onAuth });
function AuthView({ loading, pluginName, pluginIcon, i18n, handleAuth, renderForm = defaultRenderForm }) {
  return u3("div", { className: "uppy-Provider-auth", children: [u3("div", { className: "uppy-Provider-authIcon", children: pluginIcon() }), u3("div", { className: "uppy-Provider-authTitle", children: i18n("authenticateWithTitle", {
    pluginName
  }) }), renderForm({ pluginName, i18n, loading, onAuth: handleAuth })] });
}

// node_modules/@uppy/utils/lib/remoteFileObjToLocal.js
function remoteFileObjToLocal(file) {
  return {
    ...file,
    type: file.mimeType,
    extension: file.name ? getFileNameAndExtension(file.name).extension : null
  };
}

// node_modules/@uppy/provider-views/lib/ProviderView/ProviderView.js
var import_classnames4 = __toESM(require_classnames(), 1);

// node_modules/@uppy/provider-views/package.json
var package_default4 = {
  name: "@uppy/provider-views",
  description: "View library for Uppy remote provider plugins.",
  version: "4.5.3",
  license: "MIT",
  main: "lib/index.js",
  style: "dist/style.min.css",
  type: "module",
  scripts: {
    build: "tsc --build tsconfig.build.json",
    "build:css": "sass --load-path=../../ src/style.scss dist/style.css && postcss dist/style.css -u cssnano -o dist/style.min.css",
    typecheck: "tsc --build",
    test: "vitest run --environment=jsdom --silent='passed-only'"
  },
  keywords: [
    "file uploader",
    "uppy"
  ],
  homepage: "https://uppy.io",
  bugs: {
    url: "https://github.com/transloadit/uppy/issues"
  },
  repository: {
    type: "git",
    url: "git+https://github.com/transloadit/uppy.git"
  },
  files: [
    "src",
    "lib",
    "dist",
    "CHANGELOG.md"
  ],
  dependencies: {
    "@uppy/utils": "^6.2.2",
    classnames: "^2.2.6",
    nanoid: "^5.0.9",
    "p-queue": "^8.0.0",
    preact: "^10.5.13"
  },
  devDependencies: {
    "@types/gapi": "^0.0.47",
    "@types/google.accounts": "^0.0.14",
    "@types/google.picker": "^0.0.42",
    cssnano: "^7.0.7",
    jsdom: "^26.1.0",
    postcss: "^8.5.6",
    "postcss-cli": "^11.0.1",
    sass: "^1.89.2",
    typescript: "^5.8.3",
    vitest: "^3.2.4"
  },
  peerDependencies: {
    "@uppy/core": "^4.5.3"
  }
};

// node_modules/@uppy/utils/lib/VirtualList.js
var STYLE_INNER = {
  position: "relative",
  // Disabled for our use case: the wrapper elements around FileList already deal with overflow,
  // and this additional property would hide things that we want to show.
  //
  // overflow: 'hidden',
  width: "100%",
  minHeight: "100%"
};
var STYLE_CONTENT = {
  position: "absolute",
  top: 0,
  left: 0,
  // Because the `top` value gets set to some offset, this `height` being 100% would make the scrollbar
  // stretch far beyond the content. For our use case, the content div actually can get its height from
  // the elements inside it, so we don't need to specify a `height` property at all.
  //
  // height: '100%',
  width: "100%",
  overflow: "visible"
};
var VirtualList = class extends C {
  constructor(props) {
    super(props);
    __publicField(this, "handleScroll", () => {
      this.setState({ offset: this.base.scrollTop });
    });
    __publicField(this, "handleResize", () => {
      this.resize();
    });
    this.focusElement = null;
    this.state = {
      offset: 0,
      height: 0
    };
  }
  componentDidMount() {
    this.resize();
    window.addEventListener("resize", this.handleResize);
  }
  // TODO: refactor to stable lifecycle method
  componentWillUpdate() {
    if (this.base.contains(document.activeElement)) {
      this.focusElement = document.activeElement;
    }
  }
  componentDidUpdate() {
    if (this.focusElement?.parentNode && document.activeElement !== this.focusElement) {
      this.focusElement.focus();
    }
    this.focusElement = null;
    this.resize();
  }
  componentWillUnmount() {
    window.removeEventListener("resize", this.handleResize);
  }
  resize() {
    const { height } = this.state;
    if (height !== this.base.offsetHeight) {
      this.setState({
        height: this.base.offsetHeight
      });
    }
  }
  render({ data, rowHeight, renderRow, overscanCount = 10, ...props }) {
    const { offset, height } = this.state;
    let start = Math.floor(offset / rowHeight);
    let visibleRowCount = Math.floor(height / rowHeight);
    if (overscanCount) {
      start = Math.max(0, start - start % overscanCount);
      visibleRowCount += overscanCount;
    }
    const end = start + visibleRowCount + 4;
    const selection = data.slice(start, end);
    const styleInner = { ...STYLE_INNER, height: data.length * rowHeight };
    const styleContent = { ...STYLE_CONTENT, top: start * rowHeight };
    return u3("div", { onScroll: this.handleScroll, ...props, children: u3("div", { role: "presentation", style: styleInner, children: u3("div", { role: "presentation", style: styleContent, children: selection.map(renderRow) }) }) });
  }
};
var VirtualList_default = VirtualList;

// node_modules/@uppy/provider-views/lib/Item/index.js
var import_classnames = __toESM(require_classnames(), 1);

// node_modules/@uppy/provider-views/lib/Item/components/ItemIcon.js
function FileIcon() {
  return u3("svg", { "aria-hidden": "true", focusable: "false", className: "uppy-c-icon", width: 11, height: 14.5, viewBox: "0 0 44 58", children: u3("path", { d: "M27.437.517a1 1 0 0 0-.094.03H4.25C2.037.548.217 2.368.217 4.58v48.405c0 2.212 1.82 4.03 4.03 4.03H39.03c2.21 0 4.03-1.818 4.03-4.03V15.61a1 1 0 0 0-.03-.28 1 1 0 0 0 0-.093 1 1 0 0 0-.03-.032 1 1 0 0 0 0-.03 1 1 0 0 0-.032-.063 1 1 0 0 0-.03-.063 1 1 0 0 0-.032 0 1 1 0 0 0-.03-.063 1 1 0 0 0-.032-.03 1 1 0 0 0-.03-.063 1 1 0 0 0-.063-.062l-14.593-14a1 1 0 0 0-.062-.062A1 1 0 0 0 28 .708a1 1 0 0 0-.374-.157 1 1 0 0 0-.156 0 1 1 0 0 0-.03-.03l-.003-.003zM4.25 2.547h22.218v9.97c0 2.21 1.82 4.03 4.03 4.03h10.564v36.438a2.02 2.02 0 0 1-2.032 2.032H4.25c-1.13 0-2.032-.9-2.032-2.032V4.58c0-1.13.902-2.032 2.03-2.032zm24.218 1.345l10.375 9.937.75.718H30.5c-1.13 0-2.032-.9-2.032-2.03V3.89z" }) });
}
function FolderIcon() {
  return u3("svg", { "aria-hidden": "true", focusable: "false", className: "uppy-c-icon", style: { minWidth: 16, marginRight: 3 }, viewBox: "0 0 276.157 276.157", children: u3("path", { d: "M273.08 101.378c-3.3-4.65-8.86-7.32-15.254-7.32h-24.34V67.59c0-10.2-8.3-18.5-18.5-18.5h-85.322c-3.63 0-9.295-2.875-11.436-5.805l-6.386-8.735c-4.982-6.814-15.104-11.954-23.546-11.954H58.73c-9.292 0-18.638 6.608-21.737 15.372l-2.033 5.752c-.958 2.71-4.72 5.37-7.596 5.37H18.5C8.3 49.09 0 57.39 0 67.59v167.07c0 .886.16 1.73.443 2.52.152 3.306 1.18 6.424 3.053 9.064 3.3 4.652 8.86 7.32 15.255 7.32h188.487c11.395 0 23.27-8.425 27.035-19.18l40.677-116.188c2.11-6.035 1.43-12.164-1.87-16.816zM18.5 64.088h8.864c9.295 0 18.64-6.607 21.738-15.37l2.032-5.75c.96-2.712 4.722-5.373 7.597-5.373h29.565c3.63 0 9.295 2.876 11.437 5.806l6.386 8.735c4.982 6.815 15.104 11.954 23.546 11.954h85.322c1.898 0 3.5 1.602 3.5 3.5v26.47H69.34c-11.395 0-23.27 8.423-27.035 19.178L15 191.23V67.59c0-1.898 1.603-3.5 3.5-3.5zm242.29 49.15l-40.676 116.188c-1.674 4.78-7.812 9.135-12.877 9.135H18.75c-1.447 0-2.576-.372-3.02-.997-.442-.625-.422-1.814.057-3.18l40.677-116.19c1.674-4.78 7.812-9.134 12.877-9.134h188.487c1.448 0 2.577.372 3.02.997.443.625.423 1.814-.056 3.18z" }) });
}
function VideoIcon() {
  return u3("svg", { "aria-hidden": "true", focusable: "false", style: { width: 16, marginRight: 4 }, viewBox: "0 0 58 58", children: [u3("path", { d: "M36.537 28.156l-11-7a1.005 1.005 0 0 0-1.02-.033C24.2 21.3 24 21.635 24 22v14a1 1 0 0 0 1.537.844l11-7a1.002 1.002 0 0 0 0-1.688zM26 34.18V23.82L34.137 29 26 34.18z" }), u3("path", { d: "M57 6H1a1 1 0 0 0-1 1v44a1 1 0 0 0 1 1h56a1 1 0 0 0 1-1V7a1 1 0 0 0-1-1zM10 28H2v-9h8v9zm-8 2h8v9H2v-9zm10 10V8h34v42H12V40zm44-12h-8v-9h8v9zm-8 2h8v9h-8v-9zm8-22v9h-8V8h8zM2 8h8v9H2V8zm0 42v-9h8v9H2zm54 0h-8v-9h8v9z" })] });
}
function ItemIcon({ itemIconString, alt = void 0 }) {
  if (itemIconString === null)
    return null;
  switch (itemIconString) {
    case "file":
      return u3(FileIcon, {});
    case "folder":
      return u3(FolderIcon, {});
    case "video":
      return u3(VideoIcon, {});
    default: {
      return u3("img", { src: itemIconString, alt, referrerPolicy: "no-referrer", loading: "lazy", width: 16, height: 16 });
    }
  }
}

// node_modules/@uppy/provider-views/lib/Item/components/GridItem.js
function GridItem({ file, toggleCheckbox, className, isDisabled, restrictionError, showTitles, children = null, i18n }) {
  return u3("li", { className, title: isDisabled && restrictionError ? restrictionError : void 0, children: [u3("input", { type: "checkbox", className: "uppy-u-reset uppy-ProviderBrowserItem-checkbox uppy-ProviderBrowserItem-checkbox--grid", onChange: toggleCheckbox, name: "listitem", id: file.id, checked: file.status === "checked", disabled: isDisabled, "data-uppy-super-focusable": true }), u3("label", { htmlFor: file.id, "aria-label": file.data.name ?? i18n("unnamed"), className: "uppy-u-reset uppy-ProviderBrowserItem-inner", children: [u3(ItemIcon, { itemIconString: file.data.thumbnail || file.data.icon }), showTitles && (file.data.name ?? i18n("unnamed")), children] })] });
}
var GridItem_default = GridItem;

// node_modules/@uppy/provider-views/lib/Item/components/ListItem.js
function ListItem({ file, openFolder, className, isDisabled, restrictionError, toggleCheckbox, showTitles, i18n }) {
  return u3("li", { className, title: file.status !== "checked" && restrictionError ? restrictionError : void 0, children: [u3("input", {
    type: "checkbox",
    className: "uppy-u-reset uppy-ProviderBrowserItem-checkbox",
    onChange: toggleCheckbox,
    // for the <label/>
    name: "listitem",
    id: file.id,
    checked: file.status === "checked",
    "aria-label": file.data.isFolder ? i18n("allFilesFromFolderNamed", {
      name: file.data.name ?? i18n("unnamed")
    }) : null,
    disabled: isDisabled,
    "data-uppy-super-focusable": true
  }), file.data.isFolder ? (
    // button to open a folder
    u3("button", { type: "button", className: "uppy-u-reset uppy-c-btn uppy-ProviderBrowserItem-inner", onClick: () => openFolder(file.id), "aria-label": i18n("openFolderNamed", {
      name: file.data.name ?? i18n("unnamed")
    }), children: [u3("div", { className: "uppy-ProviderBrowserItem-iconWrap", children: u3(ItemIcon, { itemIconString: file.data.icon }) }), showTitles && file.data.name ? u3("span", { children: file.data.name }) : i18n("unnamed")] })
  ) : (
    // label for a checkbox
    u3("label", { htmlFor: file.id, className: "uppy-u-reset uppy-ProviderBrowserItem-inner", children: [u3("div", { className: "uppy-ProviderBrowserItem-iconWrap", children: u3(ItemIcon, { itemIconString: file.data.icon }) }), showTitles && (file.data.name ?? i18n("unnamed"))] })
  )] });
}

// node_modules/@uppy/provider-views/lib/Item/index.js
function Item(props) {
  const { viewType, toggleCheckbox, showTitles, i18n, openFolder, file, utmSource } = props;
  const restrictionError = file.type === "folder" ? null : file.restrictionError;
  const isDisabled = !!restrictionError && file.status !== "checked";
  const ourProps = {
    file,
    openFolder,
    toggleCheckbox,
    utmSource,
    i18n,
    viewType,
    showTitles,
    className: (0, import_classnames.default)("uppy-ProviderBrowserItem", { "uppy-ProviderBrowserItem--disabled": isDisabled }, { "uppy-ProviderBrowserItem--noPreview": file.data.icon === "video" }, { "uppy-ProviderBrowserItem--is-checked": file.status === "checked" }, { "uppy-ProviderBrowserItem--is-partial": file.status === "partial" }),
    isDisabled,
    restrictionError
  };
  switch (viewType) {
    case "grid":
      return u3(GridItem_default, { ...ourProps });
    case "list":
      return u3(ListItem, { ...ourProps });
    case "unsplash":
      return u3(GridItem_default, { ...ourProps, children: u3("a", { href: `${file.data.author.url}?utm_source=${utmSource}&utm_medium=referral`, target: "_blank", rel: "noopener noreferrer", className: "uppy-ProviderBrowserItem-author", tabIndex: -1, children: file.data.author.name }) });
    default:
      throw new Error(`There is no such type ${viewType}`);
  }
}

// node_modules/@uppy/provider-views/lib/Browser.js
function Browser(props) {
  const { displayedPartialTree, viewType, toggleCheckbox, handleScroll, showTitles, i18n, isLoading, openFolder, noResultsLabel, virtualList, utmSource } = props;
  const [isShiftKeyPressed, setIsShiftKeyPressed] = d2(false);
  h2(() => {
    const handleKeyUp = (e4) => {
      if (e4.key === "Shift")
        setIsShiftKeyPressed(false);
    };
    const handleKeyDown = (e4) => {
      if (e4.key === "Shift")
        setIsShiftKeyPressed(true);
    };
    document.addEventListener("keyup", handleKeyUp);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keyup", handleKeyUp);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, []);
  if (isLoading) {
    return u3("div", { className: "uppy-Provider-loading", children: typeof isLoading === "string" ? isLoading : i18n("loading") });
  }
  if (displayedPartialTree.length === 0) {
    return u3("div", { className: "uppy-Provider-empty", children: noResultsLabel });
  }
  const renderItem = (item) => u3(Item, { viewType, toggleCheckbox: (event) => {
    event.stopPropagation();
    event.preventDefault();
    document.getSelection()?.removeAllRanges();
    toggleCheckbox(item, isShiftKeyPressed);
  }, showTitles, i18n, openFolder, file: item, utmSource }, item.id);
  if (virtualList) {
    return u3("div", { className: "uppy-ProviderBrowser-body", children: u3(VirtualList_default, { className: "uppy-ProviderBrowser-list", data: displayedPartialTree, renderRow: renderItem, rowHeight: 35.5 }) });
  }
  return u3("div", { className: "uppy-ProviderBrowser-body", children: u3("ul", {
    className: "uppy-ProviderBrowser-list",
    onScroll: handleScroll,
    // making <ul> not focusable for firefox
    tabIndex: -1,
    children: displayedPartialTree.map(renderItem)
  }) });
}
var Browser_default = Browser;

// node_modules/@uppy/provider-views/lib/FooterActions.js
var import_classnames2 = __toESM(require_classnames(), 1);

// node_modules/@uppy/provider-views/lib/utils/PartialTreeUtils/getNumberOfSelectedFiles.js
var getNumberOfSelectedFiles = (partialTree) => {
  const checkedLeaves = partialTree.filter((item) => {
    if (item.type === "file" && item.status === "checked") {
      return true;
    }
    if (item.type === "folder" && item.status === "checked") {
      const doesItHaveChildren = partialTree.some((i4) => i4.type !== "root" && i4.parentId === item.id);
      return !doesItHaveChildren;
    }
    return false;
  });
  return checkedLeaves.length;
};
var getNumberOfSelectedFiles_default = getNumberOfSelectedFiles;

// node_modules/@uppy/provider-views/lib/FooterActions.js
function FooterActions({ cancelSelection, donePicking, i18n, partialTree, validateAggregateRestrictions }) {
  const aggregateRestrictionError = T2(() => {
    return validateAggregateRestrictions(partialTree);
  }, [partialTree, validateAggregateRestrictions]);
  const nOfSelectedFiles = T2(() => {
    return getNumberOfSelectedFiles_default(partialTree);
  }, [partialTree]);
  if (nOfSelectedFiles === 0) {
    return null;
  }
  return u3("div", { className: "uppy-ProviderBrowser-footer", children: [u3("div", { className: "uppy-ProviderBrowser-footer-buttons", children: [u3("button", { className: (0, import_classnames2.default)("uppy-u-reset uppy-c-btn uppy-c-btn-primary", {
    "uppy-c-btn--disabled": aggregateRestrictionError
  }), disabled: !!aggregateRestrictionError, onClick: donePicking, type: "button", children: i18n("selectX", {
    smart_count: nOfSelectedFiles
  }) }), u3("button", { className: "uppy-u-reset uppy-c-btn uppy-c-btn-link", onClick: cancelSelection, type: "button", children: i18n("cancel") })] }), aggregateRestrictionError && u3("div", { className: "uppy-ProviderBrowser-footer-error", children: aggregateRestrictionError })] });
}

// node_modules/@uppy/provider-views/node_modules/nanoid/non-secure/index.js
var urlAlphabet2 = "useandom-26T198340PX75pxJACKVERYMINDBUSHWOLF_GQZbfghjklqvwyzrict";
var nanoid2 = (size = 21) => {
  let id = "";
  let i4 = size | 0;
  while (i4-- > 0) {
    id += urlAlphabet2[Math.random() * 64 | 0];
  }
  return id;
};

// node_modules/@uppy/provider-views/lib/SearchInput.js
function SearchInput({ searchString, setSearchString, submitSearchString, wrapperClassName, inputClassName, inputLabel, clearSearchLabel = "", showButton = false, buttonLabel = "", buttonCSSClassName = "" }) {
  const onInput = (e4) => {
    setSearchString(e4.target.value);
  };
  const submit = q2((ev) => {
    ev.preventDefault();
    submitSearchString();
  }, [submitSearchString]);
  const [form] = d2(() => {
    const formEl = document.createElement("form");
    formEl.setAttribute("tabindex", "-1");
    formEl.id = nanoid2();
    return formEl;
  });
  h2(() => {
    document.body.appendChild(form);
    form.addEventListener("submit", submit);
    return () => {
      form.removeEventListener("submit", submit);
      document.body.removeChild(form);
    };
  }, [form, submit]);
  return u3("section", { className: wrapperClassName, children: [u3("input", { className: `uppy-u-reset ${inputClassName}`, type: "search", "aria-label": inputLabel, placeholder: inputLabel, value: searchString, onInput, form: form.id, "data-uppy-super-focusable": true }), !showButton && // 🔍
  u3("svg", { "aria-hidden": "true", focusable: "false", className: "uppy-c-icon uppy-ProviderBrowser-searchFilterIcon", width: "12", height: "12", viewBox: "0 0 12 12", children: u3("path", { d: "M8.638 7.99l3.172 3.172a.492.492 0 1 1-.697.697L7.91 8.656a4.977 4.977 0 0 1-2.983.983C2.206 9.639 0 7.481 0 4.819 0 2.158 2.206 0 4.927 0c2.721 0 4.927 2.158 4.927 4.82a4.74 4.74 0 0 1-1.216 3.17zm-3.71.685c2.176 0 3.94-1.726 3.94-3.856 0-2.129-1.764-3.855-3.94-3.855C2.75.964.984 2.69.984 4.819c0 2.13 1.765 3.856 3.942 3.856z" }) }), !showButton && searchString && // ❌
  u3("button", { className: "uppy-u-reset uppy-ProviderBrowser-searchFilterReset", type: "button", "aria-label": clearSearchLabel, title: clearSearchLabel, onClick: () => setSearchString(""), children: u3("svg", { "aria-hidden": "true", focusable: "false", className: "uppy-c-icon", viewBox: "0 0 19 19", children: u3("path", { d: "M17.318 17.232L9.94 9.854 9.586 9.5l-.354.354-7.378 7.378h.707l-.62-.62v.706L9.318 9.94l.354-.354-.354-.354L1.94 1.854v.707l.62-.62h-.706l7.378 7.378.354.354.354-.354 7.378-7.378h-.707l.622.62v-.706L9.854 9.232l-.354.354.354.354 7.378 7.378.708-.707-7.38-7.378v.708l7.38-7.38.353-.353-.353-.353-.622-.622-.353-.353-.354.352-7.378 7.38h.708L2.56 1.23 2.208.88l-.353.353-.622.62-.353.355.352.353 7.38 7.38v-.708l-7.38 7.38-.353.353.352.353.622.622.353.353.354-.353 7.38-7.38h-.708l7.38 7.38z" }) }) }), showButton && u3("button", { className: `uppy-u-reset uppy-c-btn uppy-c-btn-primary ${buttonCSSClassName}`, type: "submit", form: form.id, children: buttonLabel })] });
}
var SearchInput_default = SearchInput;

// node_modules/@uppy/provider-views/lib/utils/getTagFile.js
var getTagFile = (file, plugin, provider) => {
  const tagFile = {
    id: file.id,
    source: plugin.id,
    name: file.name || file.id,
    type: file.mimeType,
    isRemote: true,
    data: file,
    preview: file.thumbnail || void 0,
    meta: {
      authorName: file.author?.name,
      authorUrl: file.author?.url,
      // We need to do this `|| null` check, because null value
      // for .relDirPath is `undefined` and for .relativePath is `null`.
      // I do think we should just use `null` everywhere.
      relativePath: file.relDirPath || null,
      absolutePath: file.absDirPath
    },
    body: {
      fileId: file.id
    },
    remote: {
      companionUrl: plugin.opts.companionUrl,
      url: `${provider.fileUrl(file.requestPath)}`,
      body: {
        fileId: file.id
      },
      providerName: provider.name,
      provider: provider.provider,
      requestClientId: provider.provider
    }
  };
  return tagFile;
};
var getTagFile_default = getTagFile;

// node_modules/@uppy/provider-views/lib/utils/addFiles.js
var addFiles = (companionFiles, plugin, provider) => {
  const tagFiles = companionFiles.map((f5) => getTagFile_default(f5, plugin, provider));
  const filesToAdd = [];
  const filesAlreadyAdded = [];
  tagFiles.forEach((tagFile) => {
    if (plugin.uppy.checkIfFileAlreadyExists(getSafeFileId(tagFile, plugin.uppy.getID()))) {
      filesAlreadyAdded.push(tagFile);
    } else {
      filesToAdd.push(tagFile);
    }
  });
  if (filesToAdd.length > 0) {
    plugin.uppy.info(plugin.uppy.i18n("addedNumFiles", { numFiles: filesToAdd.length }));
  }
  if (filesAlreadyAdded.length > 0) {
    plugin.uppy.info(`Not adding ${filesAlreadyAdded.length} files because they already exist`);
  }
  plugin.uppy.addFiles(filesToAdd);
};
var addFiles_default = addFiles;

// node_modules/@uppy/provider-views/lib/utils/getClickedRange.js
var getClickedRange = (clickedId, displayedPartialTree, isShiftKeyPressed, lastCheckbox) => {
  const lastCheckboxIndex = displayedPartialTree.findIndex((item) => item.id === lastCheckbox);
  if (lastCheckboxIndex !== -1 && isShiftKeyPressed) {
    const newCheckboxIndex = displayedPartialTree.findIndex((item) => item.id === clickedId);
    const clickedRange = displayedPartialTree.slice(Math.min(lastCheckboxIndex, newCheckboxIndex), Math.max(lastCheckboxIndex, newCheckboxIndex) + 1);
    return clickedRange.map((item) => item.id);
  }
  return [clickedId];
};
var getClickedRange_default = getClickedRange;

// node_modules/@uppy/provider-views/lib/utils/handleError.js
var handleError = (uppy) => (error) => {
  if (error.isAuthError) {
    return;
  }
  if (error.name === "AbortError") {
    uppy.log("Aborting request", "warning");
    return;
  }
  uppy.log(error, "error");
  if (error.name === "UserFacingApiError") {
    uppy.info({
      message: uppy.i18n("companionError"),
      details: uppy.i18n(error.message)
    }, "warning", 5e3);
  }
};
var handleError_default = handleError;

// node_modules/@uppy/provider-views/lib/utils/PartialTreeUtils/getBreadcrumbs.js
var getBreadcrumbs = (partialTree, currentFolderId) => {
  let folder = partialTree.find((f5) => f5.id === currentFolderId);
  let breadcrumbs = [];
  while (true) {
    breadcrumbs = [folder, ...breadcrumbs];
    if (folder.type === "root")
      break;
    const currentParentId = folder.parentId;
    folder = partialTree.find((f5) => f5.id === currentParentId);
  }
  return breadcrumbs;
};
var getBreadcrumbs_default = getBreadcrumbs;

// node_modules/@uppy/provider-views/lib/utils/PartialTreeUtils/getCheckedFilesWithPaths.js
var getPath = (partialTree, id, cache) => {
  const sId = id === null ? "null" : id;
  if (cache[sId])
    return cache[sId];
  const file = partialTree.find((f5) => f5.id === id);
  if (file.type === "root")
    return [];
  const meAndParentPath = [...getPath(partialTree, file.parentId, cache), file];
  cache[sId] = meAndParentPath;
  return meAndParentPath;
};
var getCheckedFilesWithPaths = (partialTree) => {
  const cache = /* @__PURE__ */ Object.create(null);
  const checkedFiles = partialTree.filter((item) => item.type === "file" && item.status === "checked");
  const companionFilesWithInjectedPaths = checkedFiles.map((file) => {
    const absFolders = getPath(partialTree, file.id, cache);
    const firstCheckedFolderIndex = absFolders.findIndex((i4) => i4.type === "folder" && i4.status === "checked");
    const relFolders = absFolders.slice(firstCheckedFolderIndex);
    const absDirPath = `/${absFolders.map((i4) => i4.data.name).join("/")}`;
    const relDirPath = relFolders.length === 1 ? (
      // Must return `undefined` (which later turns into `null` in `.getTagFile()`)
      // (https://github.com/transloadit/uppy/pull/4537#issuecomment-1629136652)
      void 0
    ) : relFolders.map((i4) => i4.data.name).join("/");
    return {
      ...file.data,
      absDirPath,
      relDirPath
    };
  });
  return companionFilesWithInjectedPaths;
};
var getCheckedFilesWithPaths_default = getCheckedFilesWithPaths;

// node_modules/eventemitter3/index.mjs
var import_index = __toESM(require_eventemitter3(), 1);

// node_modules/p-timeout/index.js
var TimeoutError = class extends Error {
  constructor(message) {
    super(message);
    this.name = "TimeoutError";
  }
};
var AbortError = class extends Error {
  constructor(message) {
    super();
    this.name = "AbortError";
    this.message = message;
  }
};
var getDOMException = (errorMessage) => globalThis.DOMException === void 0 ? new AbortError(errorMessage) : new DOMException(errorMessage);
var getAbortedReason = (signal) => {
  const reason = signal.reason === void 0 ? getDOMException("This operation was aborted.") : signal.reason;
  return reason instanceof Error ? reason : getDOMException(reason);
};
function pTimeout(promise, options) {
  const {
    milliseconds,
    fallback,
    message,
    customTimers = { setTimeout, clearTimeout }
  } = options;
  let timer;
  let abortHandler;
  const wrappedPromise = new Promise((resolve, reject) => {
    if (typeof milliseconds !== "number" || Math.sign(milliseconds) !== 1) {
      throw new TypeError(`Expected \`milliseconds\` to be a positive number, got \`${milliseconds}\``);
    }
    if (options.signal) {
      const { signal } = options;
      if (signal.aborted) {
        reject(getAbortedReason(signal));
      }
      abortHandler = () => {
        reject(getAbortedReason(signal));
      };
      signal.addEventListener("abort", abortHandler, { once: true });
    }
    if (milliseconds === Number.POSITIVE_INFINITY) {
      promise.then(resolve, reject);
      return;
    }
    const timeoutError = new TimeoutError();
    timer = customTimers.setTimeout.call(void 0, () => {
      if (fallback) {
        try {
          resolve(fallback());
        } catch (error) {
          reject(error);
        }
        return;
      }
      if (typeof promise.cancel === "function") {
        promise.cancel();
      }
      if (message === false) {
        resolve();
      } else if (message instanceof Error) {
        reject(message);
      } else {
        timeoutError.message = message ?? `Promise timed out after ${milliseconds} milliseconds`;
        reject(timeoutError);
      }
    }, milliseconds);
    (async () => {
      try {
        resolve(await promise);
      } catch (error) {
        reject(error);
      }
    })();
  });
  const cancelablePromise = wrappedPromise.finally(() => {
    cancelablePromise.clear();
    if (abortHandler && options.signal) {
      options.signal.removeEventListener("abort", abortHandler);
    }
  });
  cancelablePromise.clear = () => {
    customTimers.clearTimeout.call(void 0, timer);
    timer = void 0;
  };
  return cancelablePromise;
}

// node_modules/p-queue/dist/lower-bound.js
function lowerBound(array, value, comparator) {
  let first = 0;
  let count = array.length;
  while (count > 0) {
    const step = Math.trunc(count / 2);
    let it = first + step;
    if (comparator(array[it], value) <= 0) {
      first = ++it;
      count -= step + 1;
    } else {
      count = step;
    }
  }
  return first;
}

// node_modules/p-queue/dist/priority-queue.js
var _queue;
var PriorityQueue = class {
  constructor() {
    __privateAdd(this, _queue, []);
  }
  enqueue(run, options) {
    options = {
      priority: 0,
      ...options
    };
    const element = {
      priority: options.priority,
      id: options.id,
      run
    };
    if (this.size === 0 || __privateGet(this, _queue)[this.size - 1].priority >= options.priority) {
      __privateGet(this, _queue).push(element);
      return;
    }
    const index = lowerBound(__privateGet(this, _queue), element, (a4, b3) => b3.priority - a4.priority);
    __privateGet(this, _queue).splice(index, 0, element);
  }
  setPriority(id, priority) {
    const index = __privateGet(this, _queue).findIndex((element) => element.id === id);
    if (index === -1) {
      throw new ReferenceError(`No promise function with the id "${id}" exists in the queue.`);
    }
    const [item] = __privateGet(this, _queue).splice(index, 1);
    this.enqueue(item.run, { priority, id });
  }
  dequeue() {
    const item = __privateGet(this, _queue).shift();
    return item?.run;
  }
  filter(options) {
    return __privateGet(this, _queue).filter((element) => element.priority === options.priority).map((element) => element.run);
  }
  get size() {
    return __privateGet(this, _queue).length;
  }
};
_queue = new WeakMap();

// node_modules/p-queue/dist/index.js
var _carryoverConcurrencyCount, _isIntervalIgnored, _intervalCount, _intervalCap, _interval, _intervalEnd, _intervalId, _timeoutId, _queue2, _queueClass, _pending, _concurrency, _isPaused, _throwOnTimeout, _idAssigner, _PQueue_instances, doesIntervalAllowAnother_get, doesConcurrentAllowAnother_get, next_fn, onResumeInterval_fn, isIntervalPaused_get, tryToStartAnother_fn, initializeIntervalIfNeeded_fn, onInterval_fn, processQueue_fn, throwOnAbort_fn, onEvent_fn;
var PQueue = class extends import_index.default {
  // TODO: The `throwOnTimeout` option should affect the return types of `add()` and `addAll()`
  constructor(options) {
    super();
    __privateAdd(this, _PQueue_instances);
    __privateAdd(this, _carryoverConcurrencyCount);
    __privateAdd(this, _isIntervalIgnored);
    __privateAdd(this, _intervalCount, 0);
    __privateAdd(this, _intervalCap);
    __privateAdd(this, _interval);
    __privateAdd(this, _intervalEnd, 0);
    __privateAdd(this, _intervalId);
    __privateAdd(this, _timeoutId);
    __privateAdd(this, _queue2);
    __privateAdd(this, _queueClass);
    __privateAdd(this, _pending, 0);
    // The `!` is needed because of https://github.com/microsoft/TypeScript/issues/32194
    __privateAdd(this, _concurrency);
    __privateAdd(this, _isPaused);
    __privateAdd(this, _throwOnTimeout);
    // Use to assign a unique identifier to a promise function, if not explicitly specified
    __privateAdd(this, _idAssigner, 1n);
    /**
        Per-operation timeout in milliseconds. Operations fulfill once `timeout` elapses if they haven't already.
    
        Applies to each future operation.
        */
    __publicField(this, "timeout");
    options = {
      carryoverConcurrencyCount: false,
      intervalCap: Number.POSITIVE_INFINITY,
      interval: 0,
      concurrency: Number.POSITIVE_INFINITY,
      autoStart: true,
      queueClass: PriorityQueue,
      ...options
    };
    if (!(typeof options.intervalCap === "number" && options.intervalCap >= 1)) {
      throw new TypeError(`Expected \`intervalCap\` to be a number from 1 and up, got \`${options.intervalCap?.toString() ?? ""}\` (${typeof options.intervalCap})`);
    }
    if (options.interval === void 0 || !(Number.isFinite(options.interval) && options.interval >= 0)) {
      throw new TypeError(`Expected \`interval\` to be a finite number >= 0, got \`${options.interval?.toString() ?? ""}\` (${typeof options.interval})`);
    }
    __privateSet(this, _carryoverConcurrencyCount, options.carryoverConcurrencyCount);
    __privateSet(this, _isIntervalIgnored, options.intervalCap === Number.POSITIVE_INFINITY || options.interval === 0);
    __privateSet(this, _intervalCap, options.intervalCap);
    __privateSet(this, _interval, options.interval);
    __privateSet(this, _queue2, new options.queueClass());
    __privateSet(this, _queueClass, options.queueClass);
    this.concurrency = options.concurrency;
    this.timeout = options.timeout;
    __privateSet(this, _throwOnTimeout, options.throwOnTimeout === true);
    __privateSet(this, _isPaused, options.autoStart === false);
  }
  get concurrency() {
    return __privateGet(this, _concurrency);
  }
  set concurrency(newConcurrency) {
    if (!(typeof newConcurrency === "number" && newConcurrency >= 1)) {
      throw new TypeError(`Expected \`concurrency\` to be a number from 1 and up, got \`${newConcurrency}\` (${typeof newConcurrency})`);
    }
    __privateSet(this, _concurrency, newConcurrency);
    __privateMethod(this, _PQueue_instances, processQueue_fn).call(this);
  }
  /**
      Updates the priority of a promise function by its id, affecting its execution order. Requires a defined concurrency limit to take effect.
  
      For example, this can be used to prioritize a promise function to run earlier.
  
      ```js
      import PQueue from 'p-queue';
  
      const queue = new PQueue({concurrency: 1});
  
      queue.add(async () => '🦄', {priority: 1});
      queue.add(async () => '🦀', {priority: 0, id: '🦀'});
      queue.add(async () => '🦄', {priority: 1});
      queue.add(async () => '🦄', {priority: 1});
  
      queue.setPriority('🦀', 2);
      ```
  
      In this case, the promise function with `id: '🦀'` runs second.
  
      You can also deprioritize a promise function to delay its execution:
  
      ```js
      import PQueue from 'p-queue';
  
      const queue = new PQueue({concurrency: 1});
  
      queue.add(async () => '🦄', {priority: 1});
      queue.add(async () => '🦀', {priority: 1, id: '🦀'});
      queue.add(async () => '🦄');
      queue.add(async () => '🦄', {priority: 0});
  
      queue.setPriority('🦀', -1);
      ```
      Here, the promise function with `id: '🦀'` executes last.
      */
  setPriority(id, priority) {
    __privateGet(this, _queue2).setPriority(id, priority);
  }
  async add(function_, options = {}) {
    options.id ?? (options.id = (__privateWrapper(this, _idAssigner)._++).toString());
    options = {
      timeout: this.timeout,
      throwOnTimeout: __privateGet(this, _throwOnTimeout),
      ...options
    };
    return new Promise((resolve, reject) => {
      __privateGet(this, _queue2).enqueue(async () => {
        __privateWrapper(this, _pending)._++;
        try {
          options.signal?.throwIfAborted();
          __privateWrapper(this, _intervalCount)._++;
          let operation = function_({ signal: options.signal });
          if (options.timeout) {
            operation = pTimeout(Promise.resolve(operation), { milliseconds: options.timeout });
          }
          if (options.signal) {
            operation = Promise.race([operation, __privateMethod(this, _PQueue_instances, throwOnAbort_fn).call(this, options.signal)]);
          }
          const result = await operation;
          resolve(result);
          this.emit("completed", result);
        } catch (error) {
          if (error instanceof TimeoutError && !options.throwOnTimeout) {
            resolve();
            return;
          }
          reject(error);
          this.emit("error", error);
        } finally {
          __privateMethod(this, _PQueue_instances, next_fn).call(this);
        }
      }, options);
      this.emit("add");
      __privateMethod(this, _PQueue_instances, tryToStartAnother_fn).call(this);
    });
  }
  async addAll(functions, options) {
    return Promise.all(functions.map(async (function_) => this.add(function_, options)));
  }
  /**
  Start (or resume) executing enqueued tasks within concurrency limit. No need to call this if queue is not paused (via `options.autoStart = false` or by `.pause()` method.)
  */
  start() {
    if (!__privateGet(this, _isPaused)) {
      return this;
    }
    __privateSet(this, _isPaused, false);
    __privateMethod(this, _PQueue_instances, processQueue_fn).call(this);
    return this;
  }
  /**
  Put queue execution on hold.
  */
  pause() {
    __privateSet(this, _isPaused, true);
  }
  /**
  Clear the queue.
  */
  clear() {
    __privateSet(this, _queue2, new (__privateGet(this, _queueClass))());
  }
  /**
      Can be called multiple times. Useful if you for example add additional items at a later time.
  
      @returns A promise that settles when the queue becomes empty.
      */
  async onEmpty() {
    if (__privateGet(this, _queue2).size === 0) {
      return;
    }
    await __privateMethod(this, _PQueue_instances, onEvent_fn).call(this, "empty");
  }
  /**
      @returns A promise that settles when the queue size is less than the given limit: `queue.size < limit`.
  
      If you want to avoid having the queue grow beyond a certain size you can `await queue.onSizeLessThan()` before adding a new item.
  
      Note that this only limits the number of items waiting to start. There could still be up to `concurrency` jobs already running that this call does not include in its calculation.
      */
  async onSizeLessThan(limit) {
    if (__privateGet(this, _queue2).size < limit) {
      return;
    }
    await __privateMethod(this, _PQueue_instances, onEvent_fn).call(this, "next", () => __privateGet(this, _queue2).size < limit);
  }
  /**
      The difference with `.onEmpty` is that `.onIdle` guarantees that all work from the queue has finished. `.onEmpty` merely signals that the queue is empty, but it could mean that some promises haven't completed yet.
  
      @returns A promise that settles when the queue becomes empty, and all promises have completed; `queue.size === 0 && queue.pending === 0`.
      */
  async onIdle() {
    if (__privateGet(this, _pending) === 0 && __privateGet(this, _queue2).size === 0) {
      return;
    }
    await __privateMethod(this, _PQueue_instances, onEvent_fn).call(this, "idle");
  }
  /**
  Size of the queue, the number of queued items waiting to run.
  */
  get size() {
    return __privateGet(this, _queue2).size;
  }
  /**
      Size of the queue, filtered by the given options.
  
      For example, this can be used to find the number of items remaining in the queue with a specific priority level.
      */
  sizeBy(options) {
    return __privateGet(this, _queue2).filter(options).length;
  }
  /**
  Number of running items (no longer in the queue).
  */
  get pending() {
    return __privateGet(this, _pending);
  }
  /**
  Whether the queue is currently paused.
  */
  get isPaused() {
    return __privateGet(this, _isPaused);
  }
};
_carryoverConcurrencyCount = new WeakMap();
_isIntervalIgnored = new WeakMap();
_intervalCount = new WeakMap();
_intervalCap = new WeakMap();
_interval = new WeakMap();
_intervalEnd = new WeakMap();
_intervalId = new WeakMap();
_timeoutId = new WeakMap();
_queue2 = new WeakMap();
_queueClass = new WeakMap();
_pending = new WeakMap();
_concurrency = new WeakMap();
_isPaused = new WeakMap();
_throwOnTimeout = new WeakMap();
_idAssigner = new WeakMap();
_PQueue_instances = new WeakSet();
doesIntervalAllowAnother_get = function() {
  return __privateGet(this, _isIntervalIgnored) || __privateGet(this, _intervalCount) < __privateGet(this, _intervalCap);
};
doesConcurrentAllowAnother_get = function() {
  return __privateGet(this, _pending) < __privateGet(this, _concurrency);
};
next_fn = function() {
  __privateWrapper(this, _pending)._--;
  __privateMethod(this, _PQueue_instances, tryToStartAnother_fn).call(this);
  this.emit("next");
};
onResumeInterval_fn = function() {
  __privateMethod(this, _PQueue_instances, onInterval_fn).call(this);
  __privateMethod(this, _PQueue_instances, initializeIntervalIfNeeded_fn).call(this);
  __privateSet(this, _timeoutId, void 0);
};
isIntervalPaused_get = function() {
  const now = Date.now();
  if (__privateGet(this, _intervalId) === void 0) {
    const delay = __privateGet(this, _intervalEnd) - now;
    if (delay < 0) {
      __privateSet(this, _intervalCount, __privateGet(this, _carryoverConcurrencyCount) ? __privateGet(this, _pending) : 0);
    } else {
      if (__privateGet(this, _timeoutId) === void 0) {
        __privateSet(this, _timeoutId, setTimeout(() => {
          __privateMethod(this, _PQueue_instances, onResumeInterval_fn).call(this);
        }, delay));
      }
      return true;
    }
  }
  return false;
};
tryToStartAnother_fn = function() {
  if (__privateGet(this, _queue2).size === 0) {
    if (__privateGet(this, _intervalId)) {
      clearInterval(__privateGet(this, _intervalId));
    }
    __privateSet(this, _intervalId, void 0);
    this.emit("empty");
    if (__privateGet(this, _pending) === 0) {
      this.emit("idle");
    }
    return false;
  }
  if (!__privateGet(this, _isPaused)) {
    const canInitializeInterval = !__privateGet(this, _PQueue_instances, isIntervalPaused_get);
    if (__privateGet(this, _PQueue_instances, doesIntervalAllowAnother_get) && __privateGet(this, _PQueue_instances, doesConcurrentAllowAnother_get)) {
      const job = __privateGet(this, _queue2).dequeue();
      if (!job) {
        return false;
      }
      this.emit("active");
      job();
      if (canInitializeInterval) {
        __privateMethod(this, _PQueue_instances, initializeIntervalIfNeeded_fn).call(this);
      }
      return true;
    }
  }
  return false;
};
initializeIntervalIfNeeded_fn = function() {
  if (__privateGet(this, _isIntervalIgnored) || __privateGet(this, _intervalId) !== void 0) {
    return;
  }
  __privateSet(this, _intervalId, setInterval(() => {
    __privateMethod(this, _PQueue_instances, onInterval_fn).call(this);
  }, __privateGet(this, _interval)));
  __privateSet(this, _intervalEnd, Date.now() + __privateGet(this, _interval));
};
onInterval_fn = function() {
  if (__privateGet(this, _intervalCount) === 0 && __privateGet(this, _pending) === 0 && __privateGet(this, _intervalId)) {
    clearInterval(__privateGet(this, _intervalId));
    __privateSet(this, _intervalId, void 0);
  }
  __privateSet(this, _intervalCount, __privateGet(this, _carryoverConcurrencyCount) ? __privateGet(this, _pending) : 0);
  __privateMethod(this, _PQueue_instances, processQueue_fn).call(this);
};
/**
Executes all queued functions until it reaches the limit.
*/
processQueue_fn = function() {
  while (__privateMethod(this, _PQueue_instances, tryToStartAnother_fn).call(this)) {
  }
};
throwOnAbort_fn = async function(signal) {
  return new Promise((_resolve, reject) => {
    signal.addEventListener("abort", () => {
      reject(signal.reason);
    }, { once: true });
  });
};
onEvent_fn = async function(event, filter) {
  return new Promise((resolve) => {
    const listener = () => {
      if (filter && !filter()) {
        return;
      }
      this.off(event, listener);
      resolve();
    };
    this.on(event, listener);
  });
};

// node_modules/@uppy/provider-views/lib/utils/PartialTreeUtils/shallowClone.js
var shallowClone = (partialTree) => {
  return partialTree.map((item) => ({ ...item }));
};
var shallowClone_default = shallowClone;

// node_modules/@uppy/provider-views/lib/utils/PartialTreeUtils/afterFill.js
var recursivelyFetch = async (queue, poorTree, poorFolder, apiList, validateSingleFile) => {
  let items = [];
  let currentPath = poorFolder.cached ? poorFolder.nextPagePath : poorFolder.id;
  while (currentPath) {
    const response = await apiList(currentPath);
    items = items.concat(response.items);
    currentPath = response.nextPagePath;
  }
  const newFolders = items.filter((i4) => i4.isFolder === true);
  const newFiles = items.filter((i4) => i4.isFolder === false);
  const folders = newFolders.map((folder) => ({
    type: "folder",
    id: folder.requestPath,
    cached: false,
    nextPagePath: null,
    status: "checked",
    parentId: poorFolder.id,
    data: folder
  }));
  const files = newFiles.map((file) => {
    const restrictionError = validateSingleFile(file);
    return {
      type: "file",
      id: file.requestPath,
      restrictionError,
      status: restrictionError ? "unchecked" : "checked",
      parentId: poorFolder.id,
      data: file
    };
  });
  poorFolder.cached = true;
  poorFolder.nextPagePath = null;
  poorTree.push(...files, ...folders);
  folders.forEach(async (folder) => {
    queue.add(() => recursivelyFetch(queue, poorTree, folder, apiList, validateSingleFile));
  });
};
var afterFill = async (partialTree, apiList, validateSingleFile, reportProgress) => {
  const queue = new PQueue({ concurrency: 6 });
  const poorTree = shallowClone_default(partialTree);
  const poorFolders = poorTree.filter((item) => item.type === "folder" && item.status === "checked" && // either "not yet cached at all" or "some pages are left to fetch"
  (item.cached === false || item.nextPagePath));
  poorFolders.forEach((poorFolder) => {
    queue.add(() => recursivelyFetch(queue, poorTree, poorFolder, apiList, validateSingleFile));
  });
  queue.on("completed", () => {
    const nOfFilesChecked = poorTree.filter((i4) => i4.type === "file" && i4.status === "checked").length;
    reportProgress(nOfFilesChecked);
  });
  await queue.onIdle();
  return poorTree;
};
var afterFill_default = afterFill;

// node_modules/@uppy/provider-views/lib/utils/PartialTreeUtils/afterOpenFolder.js
var afterOpenFolder = (oldPartialTree, discoveredItems, clickedFolder, currentPagePath, validateSingleFile) => {
  const discoveredFolders = discoveredItems.filter((i4) => i4.isFolder === true);
  const discoveredFiles = discoveredItems.filter((i4) => i4.isFolder === false);
  const isParentFolderChecked = clickedFolder.type === "folder" && clickedFolder.status === "checked";
  const folders = discoveredFolders.map((folder) => ({
    type: "folder",
    id: folder.requestPath,
    cached: false,
    nextPagePath: null,
    status: isParentFolderChecked ? "checked" : "unchecked",
    parentId: clickedFolder.id,
    data: folder
  }));
  const files = discoveredFiles.map((file) => {
    const restrictionError = validateSingleFile(file);
    return {
      type: "file",
      id: file.requestPath,
      restrictionError,
      status: isParentFolderChecked && !restrictionError ? "checked" : "unchecked",
      parentId: clickedFolder.id,
      data: file
    };
  });
  const updatedClickedFolder = {
    ...clickedFolder,
    cached: true,
    nextPagePath: currentPagePath
  };
  const partialTreeWithUpdatedClickedFolder = oldPartialTree.map((folder) => folder.id === updatedClickedFolder.id ? updatedClickedFolder : folder);
  const newPartialTree = [
    ...partialTreeWithUpdatedClickedFolder,
    ...folders,
    ...files
  ];
  return newPartialTree;
};
var afterOpenFolder_default = afterOpenFolder;

// node_modules/@uppy/provider-views/lib/utils/PartialTreeUtils/afterScrollFolder.js
var afterScrollFolder = (oldPartialTree, currentFolderId, items, nextPagePath, validateSingleFile) => {
  const currentFolder = oldPartialTree.find((i4) => i4.id === currentFolderId);
  const newFolders = items.filter((i4) => i4.isFolder === true);
  const newFiles = items.filter((i4) => i4.isFolder === false);
  const scrolledFolder = { ...currentFolder, nextPagePath };
  const partialTreeWithUpdatedScrolledFolder = oldPartialTree.map((folder) => folder.id === scrolledFolder.id ? scrolledFolder : folder);
  const isParentFolderChecked = scrolledFolder.type === "folder" && scrolledFolder.status === "checked";
  const folders = newFolders.map((folder) => ({
    type: "folder",
    id: folder.requestPath,
    cached: false,
    nextPagePath: null,
    status: isParentFolderChecked ? "checked" : "unchecked",
    parentId: scrolledFolder.id,
    data: folder
  }));
  const files = newFiles.map((file) => {
    const restrictionError = validateSingleFile(file);
    return {
      type: "file",
      id: file.requestPath,
      restrictionError,
      status: isParentFolderChecked && !restrictionError ? "checked" : "unchecked",
      parentId: scrolledFolder.id,
      data: file
    };
  });
  const newPartialTree = [
    ...partialTreeWithUpdatedScrolledFolder,
    ...folders,
    ...files
  ];
  return newPartialTree;
};
var afterScrollFolder_default = afterScrollFolder;

// node_modules/@uppy/provider-views/lib/utils/PartialTreeUtils/afterToggleCheckbox.js
var percolateDown = (tree, id, shouldMarkAsChecked) => {
  const children = tree.filter((item) => item.type !== "root" && item.parentId === id);
  children.forEach((item) => {
    item.status = shouldMarkAsChecked && !(item.type === "file" && item.restrictionError) ? "checked" : "unchecked";
    percolateDown(tree, item.id, shouldMarkAsChecked);
  });
};
var percolateUp = (tree, id) => {
  const folder = tree.find((item) => item.id === id);
  if (folder.type === "root")
    return;
  const validChildren = tree.filter((item) => (
    // is a child
    item.type !== "root" && item.parentId === folder.id && // does pass validations
    !(item.type === "file" && item.restrictionError)
  ));
  const areAllChildrenChecked = validChildren.every((item) => item.status === "checked");
  const areAllChildrenUnchecked = validChildren.every((item) => item.status === "unchecked");
  if (areAllChildrenChecked) {
    folder.status = "checked";
  } else if (areAllChildrenUnchecked) {
    folder.status = "unchecked";
  } else {
    folder.status = "partial";
  }
  percolateUp(tree, folder.parentId);
};
var afterToggleCheckbox = (oldTree, clickedRange) => {
  const tree = shallowClone_default(oldTree);
  if (clickedRange.length >= 2) {
    const newlyCheckedItems = tree.filter((item) => item.type !== "root" && clickedRange.includes(item.id));
    newlyCheckedItems.forEach((item) => {
      if (item.type === "file") {
        item.status = item.restrictionError ? "unchecked" : "checked";
      } else {
        item.status = "checked";
      }
    });
    newlyCheckedItems.forEach((item) => {
      percolateDown(tree, item.id, true);
    });
    percolateUp(tree, newlyCheckedItems[0].parentId);
  } else {
    const clickedItem = tree.find((item) => item.id === clickedRange[0]);
    clickedItem.status = clickedItem.status === "checked" ? "unchecked" : "checked";
    percolateDown(tree, clickedItem.id, clickedItem.status === "checked");
    percolateUp(tree, clickedItem.parentId);
  }
  return tree;
};
var afterToggleCheckbox_default = afterToggleCheckbox;

// node_modules/@uppy/provider-views/lib/utils/PartialTreeUtils/index.js
var PartialTreeUtils_default = {
  afterOpenFolder: afterOpenFolder_default,
  afterScrollFolder: afterScrollFolder_default,
  afterToggleCheckbox: afterToggleCheckbox_default,
  afterFill: afterFill_default
};

// node_modules/@uppy/provider-views/lib/utils/shouldHandleScroll.js
var shouldHandleScroll = (event) => {
  const { scrollHeight, scrollTop, offsetHeight } = event.target;
  const scrollPosition = scrollHeight - (scrollTop + offsetHeight);
  return scrollPosition < 50;
};
var shouldHandleScroll_default = shouldHandleScroll;

// node_modules/@uppy/provider-views/lib/ProviderView/Header.js
var import_classnames3 = __toESM(require_classnames(), 1);

// node_modules/@uppy/provider-views/lib/Breadcrumbs.js
function Breadcrumbs(props) {
  const { openFolder, title, breadcrumbsIcon, breadcrumbs, i18n } = props;
  return u3("div", { className: "uppy-Provider-breadcrumbs", children: [u3("div", { className: "uppy-Provider-breadcrumbsIcon", children: breadcrumbsIcon }), breadcrumbs.map((folder, index) => u3(S, { children: [u3("button", { type: "button", className: "uppy-u-reset uppy-c-btn", onClick: () => openFolder(folder.id), children: folder.type === "root" ? title : folder.data.name ?? i18n("unnamed") }, folder.id), breadcrumbs.length === index + 1 ? "" : " / "] }))] });
}

// node_modules/@uppy/provider-views/lib/ProviderView/User.js
function User({ i18n, logout: logout2, username }) {
  return u3(S, { children: [username && u3("span", { className: "uppy-ProviderBrowser-user", children: username }, "username"), u3("button", { type: "button", onClick: logout2, className: "uppy-u-reset uppy-c-btn uppy-ProviderBrowser-userLogout", children: i18n("logOut") }, "logout")] });
}

// node_modules/@uppy/provider-views/lib/ProviderView/Header.js
function Header(props) {
  return u3("div", { className: "uppy-ProviderBrowser-header", children: u3("div", { className: (0, import_classnames3.default)("uppy-ProviderBrowser-headerBar", !props.showBreadcrumbs && "uppy-ProviderBrowser-headerBar--simple"), children: [props.showBreadcrumbs && u3(Breadcrumbs, { openFolder: props.openFolder, breadcrumbs: props.breadcrumbs, breadcrumbsIcon: props.pluginIcon?.(), title: props.title, i18n: props.i18n }), u3(User, { logout: props.logout, username: props.username, i18n: props.i18n })] }) });
}

// node_modules/@uppy/provider-views/lib/ProviderView/ProviderView.js
function defaultPickerIcon() {
  return u3("svg", { "aria-hidden": "true", focusable: "false", width: "30", height: "30", viewBox: "0 0 30 30", children: u3("path", { d: "M15 30c8.284 0 15-6.716 15-15 0-8.284-6.716-15-15-15C6.716 0 0 6.716 0 15c0 8.284 6.716 15 15 15zm4.258-12.676v6.846h-8.426v-6.846H5.204l9.82-12.364 9.82 12.364H19.26z" }) });
}
var getDefaultState = (rootFolderId) => ({
  authenticated: void 0,
  // we don't know yet
  partialTree: [
    {
      type: "root",
      id: rootFolderId,
      cached: false,
      nextPagePath: null
    }
  ],
  currentFolderId: rootFolderId,
  searchString: "",
  didFirstRender: false,
  username: null,
  loading: false
});
var _abortController, _ProviderView_instances, withAbort_fn;
var ProviderView = class {
  constructor(plugin, opts) {
    __privateAdd(this, _ProviderView_instances);
    __publicField(this, "plugin");
    __publicField(this, "provider");
    __publicField(this, "opts");
    __publicField(this, "isHandlingScroll", false);
    __publicField(this, "lastCheckbox", null);
    __privateAdd(this, _abortController);
    __publicField(this, "validateSingleFile", (file) => {
      const companionFile = remoteFileObjToLocal(file);
      const result = this.plugin.uppy.validateSingleFile(companionFile);
      return result;
    });
    __publicField(this, "getDisplayedPartialTree", () => {
      const { partialTree, currentFolderId, searchString } = this.plugin.getPluginState();
      const inThisFolder = partialTree.filter((item) => item.type !== "root" && item.parentId === currentFolderId);
      const filtered = searchString === "" ? inThisFolder : inThisFolder.filter((item) => (item.data.name ?? this.plugin.uppy.i18n("unnamed")).toLowerCase().indexOf(searchString.toLowerCase()) !== -1);
      return filtered;
    });
    __publicField(this, "getBreadcrumbs", () => {
      const { partialTree, currentFolderId } = this.plugin.getPluginState();
      return getBreadcrumbs_default(partialTree, currentFolderId);
    });
    __publicField(this, "getSelectedAmount", () => {
      const { partialTree } = this.plugin.getPluginState();
      return getNumberOfSelectedFiles_default(partialTree);
    });
    __publicField(this, "validateAggregateRestrictions", (partialTree) => {
      const checkedFiles = partialTree.filter((item) => item.type === "file" && item.status === "checked");
      const uppyFiles = checkedFiles.map((file) => file.data);
      return this.plugin.uppy.validateAggregateRestrictions(uppyFiles);
    });
    this.plugin = plugin;
    this.provider = opts.provider;
    const defaultOptions8 = {
      viewType: "list",
      showTitles: true,
      showFilter: true,
      showBreadcrumbs: true,
      loadAllFiles: false,
      virtualList: false
    };
    this.opts = { ...defaultOptions8, ...opts };
    this.openFolder = this.openFolder.bind(this);
    this.logout = this.logout.bind(this);
    this.handleAuth = this.handleAuth.bind(this);
    this.handleScroll = this.handleScroll.bind(this);
    this.resetPluginState = this.resetPluginState.bind(this);
    this.donePicking = this.donePicking.bind(this);
    this.render = this.render.bind(this);
    this.cancelSelection = this.cancelSelection.bind(this);
    this.toggleCheckbox = this.toggleCheckbox.bind(this);
    this.resetPluginState();
    this.plugin.uppy.on("dashboard:close-panel", this.resetPluginState);
    this.plugin.uppy.registerRequestClient(this.provider.provider, this.provider);
  }
  resetPluginState() {
    this.plugin.setPluginState(getDefaultState(this.plugin.rootFolderId));
  }
  tearDown() {
  }
  setLoading(loading) {
    this.plugin.setPluginState({ loading });
  }
  cancelSelection() {
    const { partialTree } = this.plugin.getPluginState();
    const newPartialTree = partialTree.map((item) => item.type === "root" ? item : { ...item, status: "unchecked" });
    this.plugin.setPluginState({ partialTree: newPartialTree });
  }
  async openFolder(folderId) {
    this.lastCheckbox = null;
    const { partialTree } = this.plugin.getPluginState();
    const clickedFolder = partialTree.find((folder) => folder.id === folderId);
    if (clickedFolder.cached) {
      this.plugin.setPluginState({
        currentFolderId: folderId,
        searchString: ""
      });
      return;
    }
    this.setLoading(true);
    await __privateMethod(this, _ProviderView_instances, withAbort_fn).call(this, async (signal) => {
      let currentPagePath = folderId;
      let currentItems = [];
      do {
        const { username, nextPagePath, items } = await this.provider.list(currentPagePath, { signal });
        this.plugin.setPluginState({ username });
        currentPagePath = nextPagePath;
        currentItems = currentItems.concat(items);
        this.setLoading(this.plugin.uppy.i18n("loadedXFiles", {
          numFiles: currentItems.length
        }));
      } while (this.opts.loadAllFiles && currentPagePath);
      const newPartialTree = PartialTreeUtils_default.afterOpenFolder(partialTree, currentItems, clickedFolder, currentPagePath, this.validateSingleFile);
      this.plugin.setPluginState({
        partialTree: newPartialTree,
        currentFolderId: folderId,
        searchString: ""
      });
    }).catch(handleError_default(this.plugin.uppy));
    this.setLoading(false);
  }
  /**
   * Removes session token on client side.
   */
  async logout() {
    await __privateMethod(this, _ProviderView_instances, withAbort_fn).call(this, async (signal) => {
      const res = await this.provider.logout({
        signal
      });
      if (res.ok) {
        if (!res.revoked) {
          const message = this.plugin.uppy.i18n("companionUnauthorizeHint", {
            provider: this.plugin.title,
            url: res.manual_revoke_url
          });
          this.plugin.uppy.info(message, "info", 7e3);
        }
        this.plugin.setPluginState({
          ...getDefaultState(this.plugin.rootFolderId),
          authenticated: false
        });
      }
    }).catch(handleError_default(this.plugin.uppy));
  }
  async handleAuth(authFormData) {
    await __privateMethod(this, _ProviderView_instances, withAbort_fn).call(this, async (signal) => {
      this.setLoading(true);
      await this.provider.login({ authFormData, signal });
      this.plugin.setPluginState({ authenticated: true });
      await Promise.all([
        this.provider.fetchPreAuthToken(),
        this.openFolder(this.plugin.rootFolderId)
      ]);
    }).catch(handleError_default(this.plugin.uppy));
    this.setLoading(false);
  }
  async handleScroll(event) {
    const { partialTree, currentFolderId } = this.plugin.getPluginState();
    const currentFolder = partialTree.find((i4) => i4.id === currentFolderId);
    if (shouldHandleScroll_default(event) && !this.isHandlingScroll && currentFolder.nextPagePath) {
      this.isHandlingScroll = true;
      await __privateMethod(this, _ProviderView_instances, withAbort_fn).call(this, async (signal) => {
        const { nextPagePath, items } = await this.provider.list(currentFolder.nextPagePath, { signal });
        const newPartialTree = PartialTreeUtils_default.afterScrollFolder(partialTree, currentFolderId, items, nextPagePath, this.validateSingleFile);
        this.plugin.setPluginState({ partialTree: newPartialTree });
      }).catch(handleError_default(this.plugin.uppy));
      this.isHandlingScroll = false;
    }
  }
  async donePicking() {
    const { partialTree } = this.plugin.getPluginState();
    this.setLoading(true);
    await __privateMethod(this, _ProviderView_instances, withAbort_fn).call(this, async (signal) => {
      const enrichedTree = await PartialTreeUtils_default.afterFill(partialTree, (path) => this.provider.list(path, { signal }), this.validateSingleFile, (n3) => {
        this.setLoading(this.plugin.uppy.i18n("addedNumFiles", { numFiles: n3 }));
      });
      const aggregateRestrictionError = this.validateAggregateRestrictions(enrichedTree);
      if (aggregateRestrictionError) {
        this.plugin.setPluginState({ partialTree: enrichedTree });
        return;
      }
      const companionFiles = getCheckedFilesWithPaths_default(enrichedTree);
      addFiles_default(companionFiles, this.plugin, this.provider);
      this.resetPluginState();
    }).catch(handleError_default(this.plugin.uppy));
    this.setLoading(false);
  }
  toggleCheckbox(ourItem, isShiftKeyPressed) {
    const { partialTree } = this.plugin.getPluginState();
    const clickedRange = getClickedRange_default(ourItem.id, this.getDisplayedPartialTree(), isShiftKeyPressed, this.lastCheckbox);
    const newPartialTree = PartialTreeUtils_default.afterToggleCheckbox(partialTree, clickedRange);
    this.plugin.setPluginState({ partialTree: newPartialTree });
    this.lastCheckbox = ourItem.id;
  }
  render(state, viewOptions = {}) {
    const { didFirstRender } = this.plugin.getPluginState();
    const { i18n } = this.plugin.uppy;
    if (!didFirstRender) {
      this.plugin.setPluginState({ didFirstRender: true });
      this.provider.fetchPreAuthToken();
      this.openFolder(this.plugin.rootFolderId);
    }
    const opts = { ...this.opts, ...viewOptions };
    const { authenticated, loading } = this.plugin.getPluginState();
    const pluginIcon = this.plugin.icon || defaultPickerIcon;
    if (authenticated === false) {
      return u3(AuthView, { pluginName: this.plugin.title, pluginIcon, handleAuth: this.handleAuth, i18n: this.plugin.uppy.i18n, renderForm: opts.renderAuthForm, loading });
    }
    const { partialTree, username, searchString } = this.plugin.getPluginState();
    const breadcrumbs = this.getBreadcrumbs();
    return u3("div", { className: (0, import_classnames4.default)("uppy-ProviderBrowser", `uppy-ProviderBrowser-viewType--${opts.viewType}`), children: [u3(Header, { showBreadcrumbs: opts.showBreadcrumbs, openFolder: this.openFolder, breadcrumbs, pluginIcon, title: this.plugin.title, logout: this.logout, username, i18n }), opts.showFilter && u3(SearchInput_default, { searchString, setSearchString: (s4) => {
      this.plugin.setPluginState({ searchString: s4 });
    }, submitSearchString: () => {
    }, inputLabel: i18n("filter"), clearSearchLabel: i18n("resetFilter"), wrapperClassName: "uppy-ProviderBrowser-searchFilter", inputClassName: "uppy-ProviderBrowser-searchFilterInput" }), u3(Browser_default, { toggleCheckbox: this.toggleCheckbox, displayedPartialTree: this.getDisplayedPartialTree(), openFolder: this.openFolder, virtualList: opts.virtualList, noResultsLabel: i18n("noFilesFound"), handleScroll: this.handleScroll, viewType: opts.viewType, showTitles: opts.showTitles, i18n: this.plugin.uppy.i18n, isLoading: loading, utmSource: "Companion" }), u3(FooterActions, { partialTree, donePicking: this.donePicking, cancelSelection: this.cancelSelection, i18n, validateAggregateRestrictions: this.validateAggregateRestrictions })] });
  }
};
_abortController = new WeakMap();
_ProviderView_instances = new WeakSet();
withAbort_fn = async function(op) {
  __privateGet(this, _abortController)?.abort();
  const abortController = new AbortController();
  __privateSet(this, _abortController, abortController);
  const cancelRequest = () => {
    abortController.abort();
  };
  try {
    this.plugin.uppy.on("dashboard:close-panel", cancelRequest);
    this.plugin.uppy.on("cancel-all", cancelRequest);
    await op(abortController.signal);
  } finally {
    this.plugin.uppy.off("dashboard:close-panel", cancelRequest);
    this.plugin.uppy.off("cancel-all", cancelRequest);
    __privateSet(this, _abortController, void 0);
  }
};
__publicField(ProviderView, "VERSION", package_default4.version);

// node_modules/@uppy/provider-views/lib/SearchProviderView/SearchProviderView.js
var import_classnames5 = __toESM(require_classnames(), 1);
var defaultState = {
  loading: false,
  searchString: "",
  partialTree: [
    {
      type: "root",
      id: null,
      cached: false,
      nextPagePath: null
    }
  ],
  currentFolderId: null,
  isInputMode: true
};
var defaultOptions2 = {
  viewType: "grid",
  showTitles: true,
  showFilter: true,
  utmSource: "Companion"
};
var SearchProviderView = class {
  constructor(plugin, opts) {
    __publicField(this, "plugin");
    __publicField(this, "provider");
    __publicField(this, "opts");
    __publicField(this, "isHandlingScroll", false);
    __publicField(this, "lastCheckbox", null);
    __publicField(this, "validateSingleFile", (file) => {
      const companionFile = remoteFileObjToLocal(file);
      const result = this.plugin.uppy.validateSingleFile(companionFile);
      return result;
    });
    __publicField(this, "getDisplayedPartialTree", () => {
      const { partialTree } = this.plugin.getPluginState();
      return partialTree.filter((item) => item.type !== "root");
    });
    __publicField(this, "setSearchString", (searchString) => {
      this.plugin.setPluginState({ searchString });
      if (searchString === "") {
        this.plugin.setPluginState({ partialTree: [] });
      }
    });
    __publicField(this, "validateAggregateRestrictions", (partialTree) => {
      const checkedFiles = partialTree.filter((item) => item.type === "file" && item.status === "checked");
      const uppyFiles = checkedFiles.map((file) => file.data);
      return this.plugin.uppy.validateAggregateRestrictions(uppyFiles);
    });
    this.plugin = plugin;
    this.provider = opts.provider;
    this.opts = { ...defaultOptions2, ...opts };
    this.setSearchString = this.setSearchString.bind(this);
    this.search = this.search.bind(this);
    this.resetPluginState = this.resetPluginState.bind(this);
    this.handleScroll = this.handleScroll.bind(this);
    this.donePicking = this.donePicking.bind(this);
    this.cancelSelection = this.cancelSelection.bind(this);
    this.toggleCheckbox = this.toggleCheckbox.bind(this);
    this.render = this.render.bind(this);
    this.resetPluginState();
    this.plugin.uppy.on("dashboard:close-panel", this.resetPluginState);
    this.plugin.uppy.registerRequestClient(this.provider.provider, this.provider);
  }
  tearDown() {
  }
  setLoading(loading) {
    this.plugin.setPluginState({ loading });
  }
  resetPluginState() {
    this.plugin.setPluginState(defaultState);
  }
  cancelSelection() {
    const { partialTree } = this.plugin.getPluginState();
    const newPartialTree = partialTree.map((item) => item.type === "root" ? item : { ...item, status: "unchecked" });
    this.plugin.setPluginState({ partialTree: newPartialTree });
  }
  async search() {
    const { searchString } = this.plugin.getPluginState();
    if (searchString === "")
      return;
    this.setLoading(true);
    try {
      const response = await this.provider.search(searchString);
      const newPartialTree = [
        {
          type: "root",
          id: null,
          cached: false,
          nextPagePath: response.nextPageQuery
        },
        ...response.items.map((item) => ({
          type: "file",
          id: item.requestPath,
          status: "unchecked",
          parentId: null,
          data: item
        }))
      ];
      this.plugin.setPluginState({
        partialTree: newPartialTree,
        isInputMode: false
      });
    } catch (error) {
      handleError_default(this.plugin.uppy)(error);
    }
    this.setLoading(false);
  }
  async handleScroll(event) {
    const { partialTree, searchString } = this.plugin.getPluginState();
    const root = partialTree.find((i4) => i4.type === "root");
    if (shouldHandleScroll_default(event) && !this.isHandlingScroll && root.nextPagePath) {
      this.isHandlingScroll = true;
      try {
        const response = await this.provider.search(searchString, root.nextPagePath);
        const newRoot = {
          ...root,
          nextPagePath: response.nextPageQuery
        };
        const oldItems = partialTree.filter((i4) => i4.type !== "root");
        const newPartialTree = [
          newRoot,
          ...oldItems,
          ...response.items.map((item) => ({
            type: "file",
            id: item.requestPath,
            status: "unchecked",
            parentId: null,
            data: item
          }))
        ];
        this.plugin.setPluginState({ partialTree: newPartialTree });
      } catch (error) {
        handleError_default(this.plugin.uppy)(error);
      }
      this.isHandlingScroll = false;
    }
  }
  async donePicking() {
    const { partialTree } = this.plugin.getPluginState();
    const companionFiles = getCheckedFilesWithPaths_default(partialTree);
    addFiles_default(companionFiles, this.plugin, this.provider);
    this.resetPluginState();
  }
  toggleCheckbox(ourItem, isShiftKeyPressed) {
    const { partialTree } = this.plugin.getPluginState();
    const clickedRange = getClickedRange_default(ourItem.id, this.getDisplayedPartialTree(), isShiftKeyPressed, this.lastCheckbox);
    const newPartialTree = PartialTreeUtils_default.afterToggleCheckbox(partialTree, clickedRange);
    this.plugin.setPluginState({ partialTree: newPartialTree });
    this.lastCheckbox = ourItem.id;
  }
  render(state, viewOptions = {}) {
    const { isInputMode, searchString, loading, partialTree } = this.plugin.getPluginState();
    const { i18n } = this.plugin.uppy;
    const opts = { ...this.opts, ...viewOptions };
    if (isInputMode) {
      return u3(SearchInput_default, { searchString, setSearchString: this.setSearchString, submitSearchString: this.search, inputLabel: i18n("enterTextToSearch"), buttonLabel: i18n("searchImages"), wrapperClassName: "uppy-SearchProvider", inputClassName: "uppy-c-textInput uppy-SearchProvider-input", showButton: true, buttonCSSClassName: "uppy-SearchProvider-searchButton" });
    }
    return u3("div", { className: (0, import_classnames5.default)("uppy-ProviderBrowser", `uppy-ProviderBrowser-viewType--${opts.viewType}`), children: [opts.showFilter && u3(SearchInput_default, { searchString, setSearchString: this.setSearchString, submitSearchString: this.search, inputLabel: i18n("search"), clearSearchLabel: i18n("resetSearch"), wrapperClassName: "uppy-ProviderBrowser-searchFilter", inputClassName: "uppy-ProviderBrowser-searchFilterInput" }), u3(Browser_default, { toggleCheckbox: this.toggleCheckbox, displayedPartialTree: this.getDisplayedPartialTree(), handleScroll: this.handleScroll, openFolder: async () => {
    }, noResultsLabel: i18n("noSearchResults"), viewType: opts.viewType, showTitles: opts.showTitles, isLoading: loading, i18n, virtualList: false, utmSource: this.opts.utmSource }), u3(FooterActions, { partialTree, donePicking: this.donePicking, cancelSelection: this.cancelSelection, i18n, validateAggregateRestrictions: this.validateAggregateRestrictions })] });
  }
};
__publicField(SearchProviderView, "VERSION", package_default4.version);

// node_modules/@uppy/utils/lib/emaFilter.js
function emaFilter(newValue, previousSmoothedValue, halfLife, dt) {
  if (halfLife === 0 || newValue === previousSmoothedValue)
    return newValue;
  if (dt === 0)
    return previousSmoothedValue;
  return newValue + (previousSmoothedValue - newValue) * 2 ** (-dt / halfLife);
}

// node_modules/@uppy/status-bar/package.json
var package_default5 = {
  name: "@uppy/status-bar",
  description: "A progress bar for Uppy, with many bells and whistles.",
  version: "4.2.3",
  license: "MIT",
  main: "lib/index.js",
  style: "dist/style.min.css",
  type: "module",
  scripts: {
    build: "tsc --build tsconfig.build.json",
    "build:css": "sass --load-path=../../ src/style.scss dist/style.css && postcss dist/style.css -u cssnano -o dist/style.min.css",
    typecheck: "tsc --build"
  },
  keywords: [
    "file uploader",
    "uppy",
    "uppy-plugin",
    "progress bar",
    "status bar",
    "progress",
    "upload",
    "eta",
    "speed"
  ],
  homepage: "https://uppy.io",
  bugs: {
    url: "https://github.com/transloadit/uppy/issues"
  },
  repository: {
    type: "git",
    url: "git+https://github.com/transloadit/uppy.git"
  },
  files: [
    "src",
    "lib",
    "dist",
    "CHANGELOG.md"
  ],
  dependencies: {
    "@transloadit/prettier-bytes": "^0.3.4",
    "@uppy/utils": "^6.2.2",
    classnames: "^2.2.6",
    preact: "^10.5.13"
  },
  peerDependencies: {
    "@uppy/core": "^4.5.2"
  },
  devDependencies: {
    cssnano: "^7.0.7",
    postcss: "^8.5.6",
    "postcss-cli": "^11.0.1",
    sass: "^1.89.2",
    typescript: "^5.8.3"
  }
};

// node_modules/@uppy/status-bar/lib/locale.js
var locale_default2 = {
  strings: {
    // Shown in the status bar while files are being uploaded.
    uploading: "Uploading",
    // Shown in the status bar once all files have been uploaded.
    complete: "Complete",
    // Shown in the status bar if an upload failed.
    uploadFailed: "Upload failed",
    // Shown in the status bar while the upload is paused.
    paused: "Paused",
    // Used as the label for the button that retries an upload.
    retry: "Retry",
    // Used as the label for the button that cancels an upload.
    cancel: "Cancel",
    // Used as the label for the button that pauses an upload.
    pause: "Pause",
    // Used as the label for the button that resumes an upload.
    resume: "Resume",
    // Used as the label for the button that resets the upload state after an upload
    done: "Done",
    // When `showProgressDetails` is set, shows the number of files that have been fully uploaded so far.
    filesUploadedOfTotal: {
      0: "%{complete} of %{smart_count} file uploaded",
      1: "%{complete} of %{smart_count} files uploaded"
    },
    // When `showProgressDetails` is set, shows the amount of bytes that have been uploaded so far.
    dataUploadedOfTotal: "%{complete} of %{total}",
    dataUploadedOfUnknown: "%{complete} of unknown",
    // When `showProgressDetails` is set, shows an estimation of how long the upload will take to complete.
    xTimeLeft: "%{time} left",
    // Used as the label for the button that starts an upload.
    uploadXFiles: {
      0: "Upload %{smart_count} file",
      1: "Upload %{smart_count} files"
    },
    // Used as the label for the button that starts an upload, if another upload has been started in the past
    // and new files were added later.
    uploadXNewFiles: {
      0: "Upload +%{smart_count} file",
      1: "Upload +%{smart_count} files"
    },
    upload: "Upload",
    retryUpload: "Retry upload",
    xMoreFilesAdded: {
      0: "%{smart_count} more file added",
      1: "%{smart_count} more files added"
    },
    showErrorDetails: "Show error details"
  }
};

// node_modules/@uppy/status-bar/lib/StatusBarStates.js
var StatusBarStates_default = {
  STATE_ERROR: "error",
  STATE_WAITING: "waiting",
  STATE_PREPROCESSING: "preprocessing",
  STATE_UPLOADING: "uploading",
  STATE_POSTPROCESSING: "postprocessing",
  STATE_COMPLETE: "complete"
};

// node_modules/@uppy/status-bar/lib/StatusBarUI.js
var import_classnames7 = __toESM(require_classnames(), 1);

// node_modules/@uppy/status-bar/lib/Components.js
var import_prettier_bytes2 = __toESM(require_prettierBytes(), 1);

// node_modules/@uppy/utils/lib/secondsToTime.js
function secondsToTime(rawSeconds) {
  const hours = Math.floor(rawSeconds / 3600) % 24;
  const minutes = Math.floor(rawSeconds / 60) % 60;
  const seconds = Math.floor(rawSeconds % 60);
  return { hours, minutes, seconds };
}

// node_modules/@uppy/utils/lib/prettyETA.js
function prettyETA(seconds) {
  const time = secondsToTime(seconds);
  const hoursStr = time.hours === 0 ? "" : `${time.hours}h`;
  const minutesStr = time.minutes === 0 ? "" : `${time.hours === 0 ? time.minutes : ` ${time.minutes.toString(10).padStart(2, "0")}`}m`;
  const secondsStr = time.hours !== 0 ? "" : `${time.minutes === 0 ? time.seconds : ` ${time.seconds.toString(10).padStart(2, "0")}`}s`;
  return `${hoursStr}${minutesStr}${secondsStr}`;
}

// node_modules/@uppy/status-bar/lib/Components.js
var import_classnames6 = __toESM(require_classnames(), 1);
var DOT = `\xB7`;
var renderDot = () => ` ${DOT} `;
function UploadBtn(props) {
  const { newFiles, isUploadStarted, recoveredState, i18n, uploadState, isSomeGhost, startUpload } = props;
  const uploadBtnClassNames = (0, import_classnames6.default)("uppy-u-reset", "uppy-c-btn", "uppy-StatusBar-actionBtn", "uppy-StatusBar-actionBtn--upload", {
    "uppy-c-btn-primary": uploadState === StatusBarStates_default.STATE_WAITING
  }, { "uppy-StatusBar-actionBtn--disabled": isSomeGhost });
  const uploadBtnText = newFiles && isUploadStarted && !recoveredState ? i18n("uploadXNewFiles", { smart_count: newFiles }) : i18n("uploadXFiles", { smart_count: newFiles });
  return u3("button", { type: "button", className: uploadBtnClassNames, "aria-label": i18n("uploadXFiles", { smart_count: newFiles }), onClick: startUpload, disabled: isSomeGhost, "data-uppy-super-focusable": true, children: uploadBtnText });
}
function RetryBtn(props) {
  const { i18n, uppy } = props;
  return u3("button", { type: "button", className: "uppy-u-reset uppy-c-btn uppy-StatusBar-actionBtn uppy-StatusBar-actionBtn--retry", "aria-label": i18n("retryUpload"), onClick: () => uppy.retryAll().catch(() => {
  }), "data-uppy-super-focusable": true, "data-cy": "retry", children: [u3("svg", { "aria-hidden": "true", focusable: "false", className: "uppy-c-icon", width: "8", height: "10", viewBox: "0 0 8 10", children: u3("path", { d: "M4 2.408a2.75 2.75 0 1 0 2.75 2.75.626.626 0 0 1 1.25.018v.023a4 4 0 1 1-4-4.041V.25a.25.25 0 0 1 .389-.208l2.299 1.533a.25.25 0 0 1 0 .416l-2.3 1.533A.25.25 0 0 1 4 3.316v-.908z" }) }), i18n("retry")] });
}
function CancelBtn(props) {
  const { i18n, uppy } = props;
  return u3("button", { type: "button", className: "uppy-u-reset uppy-StatusBar-actionCircleBtn", title: i18n("cancel"), "aria-label": i18n("cancel"), onClick: () => uppy.cancelAll(), "data-cy": "cancel", "data-uppy-super-focusable": true, children: u3("svg", { "aria-hidden": "true", focusable: "false", className: "uppy-c-icon", width: "16", height: "16", viewBox: "0 0 16 16", children: u3("g", { fill: "none", fillRule: "evenodd", children: [u3("circle", { fill: "#888", cx: "8", cy: "8", r: "8" }), u3("path", { fill: "#FFF", d: "M9.283 8l2.567 2.567-1.283 1.283L8 9.283 5.433 11.85 4.15 10.567 6.717 8 4.15 5.433 5.433 4.15 8 6.717l2.567-2.567 1.283 1.283z" })] }) }) });
}
function PauseResumeButton(props) {
  const { isAllPaused, i18n, isAllComplete, resumableUploads, uppy } = props;
  const title = isAllPaused ? i18n("resume") : i18n("pause");
  function togglePauseResume() {
    if (isAllComplete)
      return;
    if (!resumableUploads) {
      uppy.cancelAll();
      return;
    }
    if (isAllPaused) {
      uppy.resumeAll();
      return;
    }
    uppy.pauseAll();
  }
  return u3("button", { title, "aria-label": title, className: "uppy-u-reset uppy-StatusBar-actionCircleBtn", type: "button", onClick: togglePauseResume, "data-cy": "togglePauseResume", "data-uppy-super-focusable": true, children: u3("svg", { "aria-hidden": "true", focusable: "false", className: "uppy-c-icon", width: "16", height: "16", viewBox: "0 0 16 16", children: u3("g", { fill: "none", fillRule: "evenodd", children: [u3("circle", { fill: "#888", cx: "8", cy: "8", r: "8" }), u3("path", { fill: "#FFF", d: isAllPaused ? "M6 4.25L11.5 8 6 11.75z" : "M5 4.5h2v7H5v-7zm4 0h2v7H9v-7z" })] }) }) });
}
function DoneBtn(props) {
  const { i18n, doneButtonHandler } = props;
  return u3("button", { type: "button", className: "uppy-u-reset uppy-c-btn uppy-StatusBar-actionBtn uppy-StatusBar-actionBtn--done", onClick: doneButtonHandler, "data-uppy-super-focusable": true, children: i18n("done") });
}
function LoadingSpinner() {
  return u3("svg", { className: "uppy-StatusBar-spinner", "aria-hidden": "true", focusable: "false", width: "14", height: "14", children: u3("path", { d: "M13.983 6.547c-.12-2.509-1.64-4.893-3.939-5.936-2.48-1.127-5.488-.656-7.556 1.094C.524 3.367-.398 6.048.162 8.562c.556 2.495 2.46 4.52 4.94 5.183 2.932.784 5.61-.602 7.256-3.015-1.493 1.993-3.745 3.309-6.298 2.868-2.514-.434-4.578-2.349-5.153-4.84a6.226 6.226 0 0 1 2.98-6.778C6.34.586 9.74 1.1 11.373 3.493c.407.596.693 1.282.842 1.988.127.598.073 1.197.161 1.794.078.525.543 1.257 1.15.864.525-.341.49-1.05.456-1.592-.007-.15.02.3 0 0", fillRule: "evenodd" }) });
}
function ProgressBarProcessing(props) {
  const { progress } = props;
  const { value, mode, message } = progress;
  const dot = `\xB7`;
  return u3("div", { className: "uppy-StatusBar-content", children: [u3(LoadingSpinner, {}), mode === "determinate" ? `${Math.round(value * 100)}% ${dot} ` : "", message] });
}
function ProgressDetails(props) {
  const { numUploads, complete, totalUploadedSize, totalSize, totalETA, i18n } = props;
  const ifShowFilesUploadedOfTotal = numUploads > 1;
  const totalUploadedSizeStr = (0, import_prettier_bytes2.default)(totalUploadedSize);
  return u3("div", { className: "uppy-StatusBar-statusSecondary", children: [ifShowFilesUploadedOfTotal && i18n("filesUploadedOfTotal", {
    complete,
    smart_count: numUploads
  }), u3("span", { className: "uppy-StatusBar-additionalInfo", children: [ifShowFilesUploadedOfTotal && renderDot(), totalSize != null ? i18n("dataUploadedOfTotal", {
    complete: totalUploadedSizeStr,
    total: (0, import_prettier_bytes2.default)(totalSize)
  }) : i18n("dataUploadedOfUnknown", { complete: totalUploadedSizeStr }), renderDot(), totalETA != null && i18n("xTimeLeft", {
    time: prettyETA(totalETA)
  })] })] });
}
function FileUploadCount(props) {
  const { i18n, complete, numUploads } = props;
  return u3("div", { className: "uppy-StatusBar-statusSecondary", children: i18n("filesUploadedOfTotal", { complete, smart_count: numUploads }) });
}
function UploadNewlyAddedFiles(props) {
  const { i18n, newFiles, startUpload } = props;
  const uploadBtnClassNames = (0, import_classnames6.default)("uppy-u-reset", "uppy-c-btn", "uppy-StatusBar-actionBtn", "uppy-StatusBar-actionBtn--uploadNewlyAdded");
  return u3("div", { className: "uppy-StatusBar-statusSecondary", children: [u3("div", { className: "uppy-StatusBar-statusSecondaryHint", children: i18n("xMoreFilesAdded", { smart_count: newFiles }) }), u3("button", { type: "button", className: uploadBtnClassNames, "aria-label": i18n("uploadXFiles", { smart_count: newFiles }), onClick: startUpload, children: i18n("upload") })] });
}
function ProgressBarUploading(props) {
  const { i18n, supportsUploadProgress: supportsUploadProgress2, totalProgress, showProgressDetails, isUploadStarted, isAllComplete, isAllPaused, newFiles, numUploads, complete, totalUploadedSize, totalSize, totalETA, startUpload } = props;
  const showUploadNewlyAddedFiles = newFiles && isUploadStarted;
  if (!isUploadStarted || isAllComplete) {
    return null;
  }
  const title = isAllPaused ? i18n("paused") : i18n("uploading");
  function renderProgressDetails() {
    if (!isAllPaused && !showUploadNewlyAddedFiles && showProgressDetails) {
      if (supportsUploadProgress2) {
        return u3(ProgressDetails, { numUploads, complete, totalUploadedSize, totalSize, totalETA, i18n });
      }
      return u3(FileUploadCount, { i18n, complete, numUploads });
    }
    return null;
  }
  return u3("div", { className: "uppy-StatusBar-content", title, children: [!isAllPaused ? u3(LoadingSpinner, {}) : null, u3("div", { className: "uppy-StatusBar-status", children: [u3("div", { className: "uppy-StatusBar-statusPrimary", children: supportsUploadProgress2 && totalProgress !== 0 ? `${title}: ${totalProgress}%` : title }), renderProgressDetails(), showUploadNewlyAddedFiles ? u3(UploadNewlyAddedFiles, { i18n, newFiles, startUpload }) : null] })] });
}
function ProgressBarComplete(props) {
  const { i18n } = props;
  return u3("div", {
    className: "uppy-StatusBar-content",
    // biome-ignore lint/a11y/useSemanticElements: ...
    role: "status",
    title: i18n("complete"),
    children: u3("div", { className: "uppy-StatusBar-status", children: u3("div", { className: "uppy-StatusBar-statusPrimary", children: [u3("svg", { "aria-hidden": "true", focusable: "false", className: "uppy-StatusBar-statusIndicator uppy-c-icon", width: "15", height: "11", viewBox: "0 0 15 11", children: u3("path", { d: "M.414 5.843L1.627 4.63l3.472 3.472L13.202 0l1.212 1.213L5.1 10.528z" }) }), i18n("complete")] }) })
  });
}
function ProgressBarError(props) {
  const { error, i18n, complete, numUploads } = props;
  function displayErrorAlert() {
    const errorMessage = `${i18n("uploadFailed")} 

 ${error}`;
    alert(errorMessage);
  }
  return u3("div", { className: "uppy-StatusBar-content", title: i18n("uploadFailed"), children: [u3("svg", { "aria-hidden": "true", focusable: "false", className: "uppy-StatusBar-statusIndicator uppy-c-icon", width: "11", height: "11", viewBox: "0 0 11 11", children: u3("path", { d: "M4.278 5.5L0 1.222 1.222 0 5.5 4.278 9.778 0 11 1.222 6.722 5.5 11 9.778 9.778 11 5.5 6.722 1.222 11 0 9.778z" }) }), u3("div", { className: "uppy-StatusBar-status", children: [u3("div", { className: "uppy-StatusBar-statusPrimary", children: [i18n("uploadFailed"), u3("button", { className: "uppy-u-reset uppy-StatusBar-details", "aria-label": i18n("showErrorDetails"), "data-microtip-position": "top-right", "data-microtip-size": "medium", onClick: displayErrorAlert, type: "button", children: "?" })] }), u3(FileUploadCount, { i18n, complete, numUploads })] })] });
}

// node_modules/@uppy/status-bar/lib/calculateProcessingProgress.js
function calculateProcessingProgress(files) {
  const values = [];
  let mode = "indeterminate";
  let message;
  for (const { progress } of Object.values(files)) {
    const { preprocess, postprocess } = progress;
    if (message == null && (preprocess || postprocess)) {
      ;
      ({ mode, message } = preprocess || postprocess);
    }
    if (preprocess?.mode === "determinate")
      values.push(preprocess.value);
    if (postprocess?.mode === "determinate")
      values.push(postprocess.value);
  }
  const value = values.reduce((total, progressValue) => {
    return total + progressValue / values.length;
  }, 0);
  return {
    mode,
    message,
    value
  };
}

// node_modules/@uppy/status-bar/lib/StatusBarUI.js
var { STATE_ERROR, STATE_WAITING, STATE_PREPROCESSING, STATE_UPLOADING, STATE_POSTPROCESSING, STATE_COMPLETE } = StatusBarStates_default;
function StatusBarUI({ newFiles, allowNewUpload, isUploadInProgress, isAllPaused, resumableUploads, error, hideUploadButton = void 0, hidePauseResumeButton = false, hideCancelButton = false, hideRetryButton = false, recoveredState, uploadState, totalProgress, files, supportsUploadProgress: supportsUploadProgress2, hideAfterFinish = false, isSomeGhost, doneButtonHandler = void 0, isUploadStarted, i18n, startUpload, uppy, isAllComplete, showProgressDetails = void 0, numUploads, complete, totalSize, totalETA, totalUploadedSize }) {
  function getProgressValue() {
    switch (uploadState) {
      case STATE_POSTPROCESSING:
      case STATE_PREPROCESSING: {
        const progress = calculateProcessingProgress(files);
        if (progress.mode === "determinate") {
          return progress.value * 100;
        }
        return totalProgress;
      }
      case STATE_ERROR: {
        return null;
      }
      case STATE_UPLOADING: {
        if (!supportsUploadProgress2) {
          return null;
        }
        return totalProgress;
      }
      default:
        return totalProgress;
    }
  }
  function getIsIndeterminate() {
    switch (uploadState) {
      case STATE_POSTPROCESSING:
      case STATE_PREPROCESSING: {
        const { mode } = calculateProcessingProgress(files);
        return mode === "indeterminate";
      }
      case STATE_UPLOADING: {
        if (!supportsUploadProgress2) {
          return true;
        }
        return false;
      }
      default:
        return false;
    }
  }
  const progressValue = getProgressValue();
  const width = progressValue ?? 100;
  const showUploadBtn = !error && newFiles && (!isUploadInProgress && !isAllPaused || recoveredState) && allowNewUpload && !hideUploadButton;
  const showCancelBtn = !hideCancelButton && uploadState !== STATE_WAITING && uploadState !== STATE_COMPLETE;
  const showPauseResumeBtn = resumableUploads && !hidePauseResumeButton && uploadState === STATE_UPLOADING;
  const showRetryBtn = error && !isAllComplete && !hideRetryButton;
  const showDoneBtn = doneButtonHandler && uploadState === STATE_COMPLETE;
  const progressClassNames = (0, import_classnames7.default)("uppy-StatusBar-progress", {
    "is-indeterminate": getIsIndeterminate()
  });
  const statusBarClassNames = (0, import_classnames7.default)("uppy-StatusBar", `is-${uploadState}`, { "has-ghosts": isSomeGhost });
  const progressBarStateEl = (() => {
    switch (uploadState) {
      case STATE_PREPROCESSING:
      case STATE_POSTPROCESSING:
        return u3(ProgressBarProcessing, { progress: calculateProcessingProgress(files) });
      case STATE_COMPLETE:
        return u3(ProgressBarComplete, { i18n });
      case STATE_ERROR:
        return u3(ProgressBarError, { error, i18n, numUploads, complete });
      case STATE_UPLOADING:
        return u3(ProgressBarUploading, { i18n, supportsUploadProgress: supportsUploadProgress2, totalProgress, showProgressDetails, isUploadStarted, isAllComplete, isAllPaused, newFiles, numUploads, complete, totalUploadedSize, totalSize, totalETA, startUpload });
      default:
        return null;
    }
  })();
  const atLeastOneAction = showUploadBtn || showRetryBtn || showPauseResumeBtn || showCancelBtn || showDoneBtn;
  const thereIsNothingInside = !atLeastOneAction && !progressBarStateEl;
  const isHidden = thereIsNothingInside || uploadState === STATE_COMPLETE && hideAfterFinish;
  if (isHidden) {
    return null;
  }
  return u3("div", { className: statusBarClassNames, children: [u3("div", { className: progressClassNames, style: { width: `${width}%` }, role: "progressbar", "aria-label": `${width}%`, "aria-valuetext": `${width}%`, "aria-valuemin": 0, "aria-valuemax": 100, "aria-valuenow": progressValue }), progressBarStateEl, u3("div", { className: "uppy-StatusBar-actions", children: [showUploadBtn ? u3(UploadBtn, { newFiles, isUploadStarted, recoveredState, i18n, isSomeGhost, startUpload, uploadState }) : null, showRetryBtn ? u3(RetryBtn, { i18n, uppy }) : null, showPauseResumeBtn ? u3(PauseResumeButton, { isAllPaused, i18n, isAllComplete, resumableUploads, uppy }) : null, showCancelBtn ? u3(CancelBtn, { i18n, uppy }) : null, showDoneBtn ? u3(DoneBtn, { i18n, doneButtonHandler }) : null] })] });
}

// node_modules/@uppy/status-bar/lib/StatusBar.js
var speedFilterHalfLife = 2e3;
var ETAFilterHalfLife = 2e3;
function getUploadingState(error, isAllComplete, recoveredState, files) {
  if (error) {
    return StatusBarStates_default.STATE_ERROR;
  }
  if (isAllComplete) {
    return StatusBarStates_default.STATE_COMPLETE;
  }
  if (recoveredState) {
    return StatusBarStates_default.STATE_WAITING;
  }
  let state = StatusBarStates_default.STATE_WAITING;
  const fileIDs = Object.keys(files);
  for (let i4 = 0; i4 < fileIDs.length; i4++) {
    const { progress } = files[fileIDs[i4]];
    if (progress.uploadStarted && !progress.uploadComplete) {
      return StatusBarStates_default.STATE_UPLOADING;
    }
    if (progress.preprocess) {
      state = StatusBarStates_default.STATE_PREPROCESSING;
    }
    if (progress.postprocess && state !== StatusBarStates_default.STATE_PREPROCESSING) {
      state = StatusBarStates_default.STATE_POSTPROCESSING;
    }
  }
  return state;
}
var defaultOptions3 = {
  hideUploadButton: false,
  hideRetryButton: false,
  hidePauseResumeButton: false,
  hideCancelButton: false,
  showProgressDetails: false,
  hideAfterFinish: true,
  doneButtonHandler: null
};
var _lastUpdateTime, _previousUploadedBytes, _previousSpeed, _previousETA, _StatusBar_instances, computeSmoothETA_fn, _onUploadStart;
var StatusBar = class extends UIPlugin_default {
  constructor(uppy, opts) {
    super(uppy, { ...defaultOptions3, ...opts });
    __privateAdd(this, _StatusBar_instances);
    __privateAdd(this, _lastUpdateTime);
    __privateAdd(this, _previousUploadedBytes);
    __privateAdd(this, _previousSpeed);
    __privateAdd(this, _previousETA);
    __publicField(this, "startUpload", () => {
      return this.uppy.upload().catch((() => {
      }));
    });
    __privateAdd(this, _onUploadStart, () => {
      const { recoveredState } = this.uppy.getState();
      __privateSet(this, _previousSpeed, null);
      __privateSet(this, _previousETA, null);
      if (recoveredState) {
        __privateSet(this, _previousUploadedBytes, Object.values(recoveredState.files).reduce((pv, { progress }) => pv + progress.bytesUploaded, 0));
        this.uppy.emit("restore-confirmed");
        return;
      }
      __privateSet(this, _lastUpdateTime, performance.now());
      __privateSet(this, _previousUploadedBytes, 0);
    });
    this.id = this.opts.id || "StatusBar";
    this.title = "StatusBar";
    this.type = "progressindicator";
    this.defaultLocale = locale_default2;
    this.i18nInit();
    this.render = this.render.bind(this);
    this.install = this.install.bind(this);
  }
  render(state) {
    const { capabilities, files, allowNewUpload, totalProgress, error, recoveredState } = state;
    const { newFiles, startedFiles, completeFiles, isUploadStarted, isAllComplete, isAllPaused, isUploadInProgress, isSomeGhost } = this.uppy.getObjectOfFilesPerState();
    const newFilesOrRecovered = recoveredState ? Object.values(files) : newFiles;
    const resumableUploads = !!capabilities.resumableUploads;
    const supportsUploadProgress2 = capabilities.uploadProgress !== false;
    let totalSize = null;
    let totalUploadedSize = 0;
    if (startedFiles.every((f5) => f5.progress.bytesTotal != null && f5.progress.bytesTotal !== 0)) {
      totalSize = 0;
      startedFiles.forEach((file) => {
        totalSize += file.progress.bytesTotal || 0;
        totalUploadedSize += file.progress.bytesUploaded || 0;
      });
    } else {
      startedFiles.forEach((file) => {
        totalUploadedSize += file.progress.bytesUploaded || 0;
      });
    }
    const totalETA = __privateMethod(this, _StatusBar_instances, computeSmoothETA_fn).call(this, {
      uploaded: totalUploadedSize,
      total: totalSize
    });
    return StatusBarUI({
      error,
      uploadState: getUploadingState(error, isAllComplete, recoveredState, state.files || {}),
      allowNewUpload,
      totalProgress,
      totalSize,
      totalUploadedSize,
      isAllComplete: false,
      isAllPaused,
      isUploadStarted,
      isUploadInProgress,
      isSomeGhost,
      recoveredState,
      complete: completeFiles.length,
      newFiles: newFilesOrRecovered.length,
      numUploads: startedFiles.length,
      totalETA,
      files,
      i18n: this.i18n,
      uppy: this.uppy,
      startUpload: this.startUpload,
      doneButtonHandler: this.opts.doneButtonHandler,
      resumableUploads,
      supportsUploadProgress: supportsUploadProgress2,
      showProgressDetails: this.opts.showProgressDetails,
      hideUploadButton: this.opts.hideUploadButton,
      hideRetryButton: this.opts.hideRetryButton,
      hidePauseResumeButton: this.opts.hidePauseResumeButton,
      hideCancelButton: this.opts.hideCancelButton,
      hideAfterFinish: this.opts.hideAfterFinish
    });
  }
  onMount() {
    const element = this.el;
    const direction = getTextDirection_default(element);
    if (!direction) {
      element.dir = "ltr";
    }
  }
  install() {
    const { target } = this.opts;
    if (target) {
      this.mount(target, this);
    }
    this.uppy.on("upload", __privateGet(this, _onUploadStart));
    __privateSet(this, _lastUpdateTime, performance.now());
    __privateSet(this, _previousUploadedBytes, this.uppy.getFiles().reduce((pv, file) => pv + file.progress.bytesUploaded, 0));
  }
  uninstall() {
    this.unmount();
    this.uppy.off("upload", __privateGet(this, _onUploadStart));
  }
};
_lastUpdateTime = new WeakMap();
_previousUploadedBytes = new WeakMap();
_previousSpeed = new WeakMap();
_previousETA = new WeakMap();
_StatusBar_instances = new WeakSet();
computeSmoothETA_fn = function(totalBytes) {
  if (totalBytes.total == null || totalBytes.total === 0) {
    return null;
  }
  const remaining = totalBytes.total - totalBytes.uploaded;
  if (remaining <= 0) {
    return null;
  }
  __privateGet(this, _lastUpdateTime) ?? __privateSet(this, _lastUpdateTime, performance.now());
  const dt = performance.now() - __privateGet(this, _lastUpdateTime);
  if (dt === 0) {
    return Math.round((__privateGet(this, _previousETA) ?? 0) / 100) / 10;
  }
  const uploadedBytesSinceLastTick = totalBytes.uploaded - __privateGet(this, _previousUploadedBytes);
  __privateSet(this, _previousUploadedBytes, totalBytes.uploaded);
  if (uploadedBytesSinceLastTick <= 0) {
    return Math.round((__privateGet(this, _previousETA) ?? 0) / 100) / 10;
  }
  const currentSpeed = uploadedBytesSinceLastTick / dt;
  const filteredSpeed = __privateGet(this, _previousSpeed) == null ? currentSpeed : emaFilter(currentSpeed, __privateGet(this, _previousSpeed), speedFilterHalfLife, dt);
  __privateSet(this, _previousSpeed, filteredSpeed);
  const instantETA = remaining / filteredSpeed;
  const updatedPreviousETA = Math.max(__privateGet(this, _previousETA) - dt, 0);
  const filteredETA = __privateGet(this, _previousETA) == null ? instantETA : emaFilter(instantETA, updatedPreviousETA, ETAFilterHalfLife, dt);
  __privateSet(this, _previousETA, filteredETA);
  __privateSet(this, _lastUpdateTime, performance.now());
  return Math.round(filteredETA / 100) / 10;
};
_onUploadStart = new WeakMap();
__publicField(StatusBar, "VERSION", package_default5.version);

// node_modules/@uppy/utils/lib/dataURItoBlob.js
var DATA_URL_PATTERN = /^data:([^/]+\/[^,;]+(?:[^,]*?))(;base64)?,([\s\S]*)$/;
function dataURItoBlob(dataURI, opts, toFile) {
  const dataURIData = DATA_URL_PATTERN.exec(dataURI);
  const mimeType = opts.mimeType ?? dataURIData?.[1] ?? "plain/text";
  let data;
  if (dataURIData?.[2] != null) {
    const binary = atob(decodeURIComponent(dataURIData[3]));
    const bytes = new Uint8Array(binary.length);
    for (let i4 = 0; i4 < binary.length; i4++) {
      bytes[i4] = binary.charCodeAt(i4);
    }
    data = [bytes];
  } else if (dataURIData?.[3] != null) {
    data = [decodeURIComponent(dataURIData[3])];
  }
  if (toFile) {
    return new File(data, opts.name || "", { type: mimeType });
  }
  return new Blob(data, { type: mimeType });
}
var dataURItoBlob_default = dataURItoBlob;

// node_modules/@uppy/utils/lib/isObjectURL.js
function isObjectURL(url) {
  return url.startsWith("blob:");
}

// node_modules/@uppy/utils/lib/isPreviewSupported.js
function isPreviewSupported(fileType) {
  if (!fileType)
    return false;
  return /^[^/]+\/(jpe?g|gif|png|svg|svg\+xml|bmp|webp|avif)$/.test(fileType);
}

// node_modules/exifr/dist/mini.esm.mjs
function e3(e4, t4, s4) {
  return t4 in e4 ? Object.defineProperty(e4, t4, { value: s4, enumerable: true, configurable: true, writable: true }) : e4[t4] = s4, e4;
}
var t3 = "undefined" != typeof self ? self : global;
var s3 = "undefined" != typeof navigator;
var i3 = s3 && "undefined" == typeof HTMLImageElement;
var n2 = !("undefined" == typeof global || "undefined" == typeof process || !process.versions || !process.versions.node);
var r3 = t3.Buffer;
var a3 = !!r3;
var h3 = (e4) => void 0 !== e4;
function f4(e4) {
  return void 0 === e4 || (e4 instanceof Map ? 0 === e4.size : 0 === Object.values(e4).filter(h3).length);
}
function l3(e4) {
  let t4 = new Error(e4);
  throw delete t4.stack, t4;
}
function o3(e4) {
  let t4 = (function(e5) {
    let t5 = 0;
    return e5.ifd0.enabled && (t5 += 1024), e5.exif.enabled && (t5 += 2048), e5.makerNote && (t5 += 2048), e5.userComment && (t5 += 1024), e5.gps.enabled && (t5 += 512), e5.interop.enabled && (t5 += 100), e5.ifd1.enabled && (t5 += 1024), t5 + 2048;
  })(e4);
  return e4.jfif.enabled && (t4 += 50), e4.xmp.enabled && (t4 += 2e4), e4.iptc.enabled && (t4 += 14e3), e4.icc.enabled && (t4 += 6e3), t4;
}
var u4 = (e4) => String.fromCharCode.apply(null, e4);
var d3 = "undefined" != typeof TextDecoder ? new TextDecoder("utf-8") : void 0;
var c3 = class _c {
  static from(e4, t4) {
    return e4 instanceof this && e4.le === t4 ? e4 : new _c(e4, void 0, void 0, t4);
  }
  constructor(e4, t4 = 0, s4, i4) {
    if ("boolean" == typeof i4 && (this.le = i4), Array.isArray(e4) && (e4 = new Uint8Array(e4)), 0 === e4) this.byteOffset = 0, this.byteLength = 0;
    else if (e4 instanceof ArrayBuffer) {
      void 0 === s4 && (s4 = e4.byteLength - t4);
      let i5 = new DataView(e4, t4, s4);
      this._swapDataView(i5);
    } else if (e4 instanceof Uint8Array || e4 instanceof DataView || e4 instanceof _c) {
      void 0 === s4 && (s4 = e4.byteLength - t4), (t4 += e4.byteOffset) + s4 > e4.byteOffset + e4.byteLength && l3("Creating view outside of available memory in ArrayBuffer");
      let i5 = new DataView(e4.buffer, t4, s4);
      this._swapDataView(i5);
    } else if ("number" == typeof e4) {
      let t5 = new DataView(new ArrayBuffer(e4));
      this._swapDataView(t5);
    } else l3("Invalid input argument for BufferView: " + e4);
  }
  _swapArrayBuffer(e4) {
    this._swapDataView(new DataView(e4));
  }
  _swapBuffer(e4) {
    this._swapDataView(new DataView(e4.buffer, e4.byteOffset, e4.byteLength));
  }
  _swapDataView(e4) {
    this.dataView = e4, this.buffer = e4.buffer, this.byteOffset = e4.byteOffset, this.byteLength = e4.byteLength;
  }
  _lengthToEnd(e4) {
    return this.byteLength - e4;
  }
  set(e4, t4, s4 = _c) {
    return e4 instanceof DataView || e4 instanceof _c ? e4 = new Uint8Array(e4.buffer, e4.byteOffset, e4.byteLength) : e4 instanceof ArrayBuffer && (e4 = new Uint8Array(e4)), e4 instanceof Uint8Array || l3("BufferView.set(): Invalid data argument."), this.toUint8().set(e4, t4), new s4(this, t4, e4.byteLength);
  }
  subarray(e4, t4) {
    return t4 = t4 || this._lengthToEnd(e4), new _c(this, e4, t4);
  }
  toUint8() {
    return new Uint8Array(this.buffer, this.byteOffset, this.byteLength);
  }
  getUint8Array(e4, t4) {
    return new Uint8Array(this.buffer, this.byteOffset + e4, t4);
  }
  getString(e4 = 0, t4 = this.byteLength) {
    let s4 = this.getUint8Array(e4, t4);
    return i4 = s4, d3 ? d3.decode(i4) : a3 ? Buffer.from(i4).toString("utf8") : decodeURIComponent(escape(u4(i4)));
    var i4;
  }
  getLatin1String(e4 = 0, t4 = this.byteLength) {
    let s4 = this.getUint8Array(e4, t4);
    return u4(s4);
  }
  getUnicodeString(e4 = 0, t4 = this.byteLength) {
    const s4 = [];
    for (let i4 = 0; i4 < t4 && e4 + i4 < this.byteLength; i4 += 2) s4.push(this.getUint16(e4 + i4));
    return u4(s4);
  }
  getInt8(e4) {
    return this.dataView.getInt8(e4);
  }
  getUint8(e4) {
    return this.dataView.getUint8(e4);
  }
  getInt16(e4, t4 = this.le) {
    return this.dataView.getInt16(e4, t4);
  }
  getInt32(e4, t4 = this.le) {
    return this.dataView.getInt32(e4, t4);
  }
  getUint16(e4, t4 = this.le) {
    return this.dataView.getUint16(e4, t4);
  }
  getUint32(e4, t4 = this.le) {
    return this.dataView.getUint32(e4, t4);
  }
  getFloat32(e4, t4 = this.le) {
    return this.dataView.getFloat32(e4, t4);
  }
  getFloat64(e4, t4 = this.le) {
    return this.dataView.getFloat64(e4, t4);
  }
  getFloat(e4, t4 = this.le) {
    return this.dataView.getFloat32(e4, t4);
  }
  getDouble(e4, t4 = this.le) {
    return this.dataView.getFloat64(e4, t4);
  }
  getUintBytes(e4, t4, s4) {
    switch (t4) {
      case 1:
        return this.getUint8(e4, s4);
      case 2:
        return this.getUint16(e4, s4);
      case 4:
        return this.getUint32(e4, s4);
      case 8:
        return this.getUint64 && this.getUint64(e4, s4);
    }
  }
  getUint(e4, t4, s4) {
    switch (t4) {
      case 8:
        return this.getUint8(e4, s4);
      case 16:
        return this.getUint16(e4, s4);
      case 32:
        return this.getUint32(e4, s4);
      case 64:
        return this.getUint64 && this.getUint64(e4, s4);
    }
  }
  toString(e4) {
    return this.dataView.toString(e4, this.constructor.name);
  }
  ensureChunk() {
  }
};
function p3(e4, t4) {
  l3(`${e4} '${t4}' was not loaded, try using full build of exifr.`);
}
var g4 = class extends Map {
  constructor(e4) {
    super(), this.kind = e4;
  }
  get(e4, t4) {
    return this.has(e4) || p3(this.kind, e4), t4 && (e4 in t4 || (function(e5, t5) {
      l3(`Unknown ${e5} '${t5}'.`);
    })(this.kind, e4), t4[e4].enabled || p3(this.kind, e4)), super.get(e4);
  }
  keyList() {
    return Array.from(this.keys());
  }
};
var m3 = new g4("file parser");
var y3 = new g4("segment parser");
var b2 = new g4("file reader");
var w3 = t3.fetch;
function k3(e4, t4) {
  return (i4 = e4).startsWith("data:") || i4.length > 1e4 ? v3(e4, t4, "base64") : n2 && e4.includes("://") ? O3(e4, t4, "url", S2) : n2 ? v3(e4, t4, "fs") : s3 ? O3(e4, t4, "url", S2) : void l3("Invalid input argument");
  var i4;
}
async function O3(e4, t4, s4, i4) {
  return b2.has(s4) ? v3(e4, t4, s4) : i4 ? (async function(e5, t5) {
    let s5 = await t5(e5);
    return new c3(s5);
  })(e4, i4) : void l3(`Parser ${s4} is not loaded`);
}
async function v3(e4, t4, s4) {
  let i4 = new (b2.get(s4))(e4, t4);
  return await i4.read(), i4;
}
var S2 = (e4) => w3(e4).then(((e5) => e5.arrayBuffer()));
var A4 = (e4) => new Promise(((t4, s4) => {
  let i4 = new FileReader();
  i4.onloadend = () => t4(i4.result || new ArrayBuffer()), i4.onerror = s4, i4.readAsArrayBuffer(e4);
}));
var U3 = class extends Map {
  get tagKeys() {
    return this.allKeys || (this.allKeys = Array.from(this.keys())), this.allKeys;
  }
  get tagValues() {
    return this.allValues || (this.allValues = Array.from(this.values())), this.allValues;
  }
};
function x3(e4, t4, s4) {
  let i4 = new U3();
  for (let [e5, t5] of s4) i4.set(e5, t5);
  if (Array.isArray(t4)) for (let s5 of t4) e4.set(s5, i4);
  else e4.set(t4, i4);
  return i4;
}
function C3(e4, t4, s4) {
  let i4, n3 = e4.get(t4);
  for (i4 of s4) n3.set(i4[0], i4[1]);
}
var B4 = /* @__PURE__ */ new Map();
var V3 = /* @__PURE__ */ new Map();
var I2 = /* @__PURE__ */ new Map();
var L2 = ["chunked", "firstChunkSize", "firstChunkSizeNode", "firstChunkSizeBrowser", "chunkSize", "chunkLimit"];
var T4 = ["jfif", "xmp", "icc", "iptc", "ihdr"];
var z3 = ["tiff", ...T4];
var P4 = ["ifd0", "ifd1", "exif", "gps", "interop"];
var F3 = [...z3, ...P4];
var j4 = ["makerNote", "userComment"];
var E3 = ["translateKeys", "translateValues", "reviveValues", "multiSegment"];
var M3 = [...E3, "sanitize", "mergeOutput", "silentErrors"];
var _3 = class {
  get translate() {
    return this.translateKeys || this.translateValues || this.reviveValues;
  }
};
var D3 = class extends _3 {
  get needed() {
    return this.enabled || this.deps.size > 0;
  }
  constructor(t4, s4, i4, n3) {
    if (super(), e3(this, "enabled", false), e3(this, "skip", /* @__PURE__ */ new Set()), e3(this, "pick", /* @__PURE__ */ new Set()), e3(this, "deps", /* @__PURE__ */ new Set()), e3(this, "translateKeys", false), e3(this, "translateValues", false), e3(this, "reviveValues", false), this.key = t4, this.enabled = s4, this.parse = this.enabled, this.applyInheritables(n3), this.canBeFiltered = P4.includes(t4), this.canBeFiltered && (this.dict = B4.get(t4)), void 0 !== i4) if (Array.isArray(i4)) this.parse = this.enabled = true, this.canBeFiltered && i4.length > 0 && this.translateTagSet(i4, this.pick);
    else if ("object" == typeof i4) {
      if (this.enabled = true, this.parse = false !== i4.parse, this.canBeFiltered) {
        let { pick: e4, skip: t5 } = i4;
        e4 && e4.length > 0 && this.translateTagSet(e4, this.pick), t5 && t5.length > 0 && this.translateTagSet(t5, this.skip);
      }
      this.applyInheritables(i4);
    } else true === i4 || false === i4 ? this.parse = this.enabled = i4 : l3(`Invalid options argument: ${i4}`);
  }
  applyInheritables(e4) {
    let t4, s4;
    for (t4 of E3) s4 = e4[t4], void 0 !== s4 && (this[t4] = s4);
  }
  translateTagSet(e4, t4) {
    if (this.dict) {
      let s4, i4, { tagKeys: n3, tagValues: r4 } = this.dict;
      for (s4 of e4) "string" == typeof s4 ? (i4 = r4.indexOf(s4), -1 === i4 && (i4 = n3.indexOf(Number(s4))), -1 !== i4 && t4.add(Number(n3[i4]))) : t4.add(s4);
    } else for (let s4 of e4) t4.add(s4);
  }
  finalizeFilters() {
    !this.enabled && this.deps.size > 0 ? (this.enabled = true, X3(this.pick, this.deps)) : this.enabled && this.pick.size > 0 && X3(this.pick, this.deps);
  }
};
var N2 = { jfif: false, tiff: true, xmp: false, icc: false, iptc: false, ifd0: true, ifd1: false, exif: true, gps: true, interop: false, ihdr: void 0, makerNote: false, userComment: false, multiSegment: false, skip: [], pick: [], translateKeys: true, translateValues: true, reviveValues: true, sanitize: true, mergeOutput: true, silentErrors: true, chunked: true, firstChunkSize: void 0, firstChunkSizeNode: 512, firstChunkSizeBrowser: 65536, chunkSize: 65536, chunkLimit: 5 };
var $2 = /* @__PURE__ */ new Map();
var R2 = class extends _3 {
  static useCached(e4) {
    let t4 = $2.get(e4);
    return void 0 !== t4 || (t4 = new this(e4), $2.set(e4, t4)), t4;
  }
  constructor(e4) {
    super(), true === e4 ? this.setupFromTrue() : void 0 === e4 ? this.setupFromUndefined() : Array.isArray(e4) ? this.setupFromArray(e4) : "object" == typeof e4 ? this.setupFromObject(e4) : l3(`Invalid options argument ${e4}`), void 0 === this.firstChunkSize && (this.firstChunkSize = s3 ? this.firstChunkSizeBrowser : this.firstChunkSizeNode), this.mergeOutput && (this.ifd1.enabled = false), this.filterNestedSegmentTags(), this.traverseTiffDependencyTree(), this.checkLoadedPlugins();
  }
  setupFromUndefined() {
    let e4;
    for (e4 of L2) this[e4] = N2[e4];
    for (e4 of M3) this[e4] = N2[e4];
    for (e4 of j4) this[e4] = N2[e4];
    for (e4 of F3) this[e4] = new D3(e4, N2[e4], void 0, this);
  }
  setupFromTrue() {
    let e4;
    for (e4 of L2) this[e4] = N2[e4];
    for (e4 of M3) this[e4] = N2[e4];
    for (e4 of j4) this[e4] = true;
    for (e4 of F3) this[e4] = new D3(e4, true, void 0, this);
  }
  setupFromArray(e4) {
    let t4;
    for (t4 of L2) this[t4] = N2[t4];
    for (t4 of M3) this[t4] = N2[t4];
    for (t4 of j4) this[t4] = N2[t4];
    for (t4 of F3) this[t4] = new D3(t4, false, void 0, this);
    this.setupGlobalFilters(e4, void 0, P4);
  }
  setupFromObject(e4) {
    let t4;
    for (t4 of (P4.ifd0 = P4.ifd0 || P4.image, P4.ifd1 = P4.ifd1 || P4.thumbnail, Object.assign(this, e4), L2)) this[t4] = W3(e4[t4], N2[t4]);
    for (t4 of M3) this[t4] = W3(e4[t4], N2[t4]);
    for (t4 of j4) this[t4] = W3(e4[t4], N2[t4]);
    for (t4 of z3) this[t4] = new D3(t4, N2[t4], e4[t4], this);
    for (t4 of P4) this[t4] = new D3(t4, N2[t4], e4[t4], this.tiff);
    this.setupGlobalFilters(e4.pick, e4.skip, P4, F3), true === e4.tiff ? this.batchEnableWithBool(P4, true) : false === e4.tiff ? this.batchEnableWithUserValue(P4, e4) : Array.isArray(e4.tiff) ? this.setupGlobalFilters(e4.tiff, void 0, P4) : "object" == typeof e4.tiff && this.setupGlobalFilters(e4.tiff.pick, e4.tiff.skip, P4);
  }
  batchEnableWithBool(e4, t4) {
    for (let s4 of e4) this[s4].enabled = t4;
  }
  batchEnableWithUserValue(e4, t4) {
    for (let s4 of e4) {
      let e5 = t4[s4];
      this[s4].enabled = false !== e5 && void 0 !== e5;
    }
  }
  setupGlobalFilters(e4, t4, s4, i4 = s4) {
    if (e4 && e4.length) {
      for (let e5 of i4) this[e5].enabled = false;
      let t5 = K3(e4, s4);
      for (let [e5, s5] of t5) X3(this[e5].pick, s5), this[e5].enabled = true;
    } else if (t4 && t4.length) {
      let e5 = K3(t4, s4);
      for (let [t5, s5] of e5) X3(this[t5].skip, s5);
    }
  }
  filterNestedSegmentTags() {
    let { ifd0: e4, exif: t4, xmp: s4, iptc: i4, icc: n3 } = this;
    this.makerNote ? t4.deps.add(37500) : t4.skip.add(37500), this.userComment ? t4.deps.add(37510) : t4.skip.add(37510), s4.enabled || e4.skip.add(700), i4.enabled || e4.skip.add(33723), n3.enabled || e4.skip.add(34675);
  }
  traverseTiffDependencyTree() {
    let { ifd0: e4, exif: t4, gps: s4, interop: i4 } = this;
    i4.needed && (t4.deps.add(40965), e4.deps.add(40965)), t4.needed && e4.deps.add(34665), s4.needed && e4.deps.add(34853), this.tiff.enabled = P4.some(((e5) => true === this[e5].enabled)) || this.makerNote || this.userComment;
    for (let e5 of P4) this[e5].finalizeFilters();
  }
  get onlyTiff() {
    return !T4.map(((e4) => this[e4].enabled)).some(((e4) => true === e4)) && this.tiff.enabled;
  }
  checkLoadedPlugins() {
    for (let e4 of z3) this[e4].enabled && !y3.has(e4) && p3("segment parser", e4);
  }
};
function K3(e4, t4) {
  let s4, i4, n3, r4, a4 = [];
  for (n3 of t4) {
    for (r4 of (s4 = B4.get(n3), i4 = [], s4)) (e4.includes(r4[0]) || e4.includes(r4[1])) && i4.push(r4[0]);
    i4.length && a4.push([n3, i4]);
  }
  return a4;
}
function W3(e4, t4) {
  return void 0 !== e4 ? e4 : void 0 !== t4 ? t4 : void 0;
}
function X3(e4, t4) {
  for (let s4 of t4) e4.add(s4);
}
e3(R2, "default", N2);
var H3 = class {
  constructor(t4) {
    e3(this, "parsers", {}), e3(this, "output", {}), e3(this, "errors", []), e3(this, "pushToErrors", ((e4) => this.errors.push(e4))), this.options = R2.useCached(t4);
  }
  async read(e4) {
    this.file = await (function(e5, t4) {
      return "string" == typeof e5 ? k3(e5, t4) : s3 && !i3 && e5 instanceof HTMLImageElement ? k3(e5.src, t4) : e5 instanceof Uint8Array || e5 instanceof ArrayBuffer || e5 instanceof DataView ? new c3(e5) : s3 && e5 instanceof Blob ? O3(e5, t4, "blob", A4) : void l3("Invalid input argument");
    })(e4, this.options);
  }
  setup() {
    if (this.fileParser) return;
    let { file: e4 } = this, t4 = e4.getUint16(0);
    for (let [s4, i4] of m3) if (i4.canHandle(e4, t4)) return this.fileParser = new i4(this.options, this.file, this.parsers), e4[s4] = true;
    this.file.close && this.file.close(), l3("Unknown file format");
  }
  async parse() {
    let { output: e4, errors: t4 } = this;
    return this.setup(), this.options.silentErrors ? (await this.executeParsers().catch(this.pushToErrors), t4.push(...this.fileParser.errors)) : await this.executeParsers(), this.file.close && this.file.close(), this.options.silentErrors && t4.length > 0 && (e4.errors = t4), f4(s4 = e4) ? void 0 : s4;
    var s4;
  }
  async executeParsers() {
    let { output: e4 } = this;
    await this.fileParser.parse();
    let t4 = Object.values(this.parsers).map((async (t5) => {
      let s4 = await t5.parse();
      t5.assignToOutput(e4, s4);
    }));
    this.options.silentErrors && (t4 = t4.map(((e5) => e5.catch(this.pushToErrors)))), await Promise.all(t4);
  }
  async extractThumbnail() {
    this.setup();
    let { options: e4, file: t4 } = this, s4 = y3.get("tiff", e4);
    var i4;
    if (t4.tiff ? i4 = { start: 0, type: "tiff" } : t4.jpeg && (i4 = await this.fileParser.getOrFindSegment("tiff")), void 0 === i4) return;
    let n3 = await this.fileParser.ensureSegmentChunk(i4), r4 = this.parsers.tiff = new s4(n3, e4, t4), a4 = await r4.extractThumbnail();
    return t4.close && t4.close(), a4;
  }
};
async function Y(e4, t4) {
  let s4 = new H3(t4);
  return await s4.read(e4), s4.parse();
}
var G3 = Object.freeze({ __proto__: null, parse: Y, Exifr: H3, fileParsers: m3, segmentParsers: y3, fileReaders: b2, tagKeys: B4, tagValues: V3, tagRevivers: I2, createDictionary: x3, extendDictionary: C3, fetchUrlAsArrayBuffer: S2, readBlobAsArrayBuffer: A4, chunkedProps: L2, otherSegments: T4, segments: z3, tiffBlocks: P4, segmentsAndBlocks: F3, tiffExtractables: j4, inheritables: E3, allFormatters: M3, Options: R2 });
var J3 = class {
  static findPosition(e4, t4) {
    let s4 = e4.getUint16(t4 + 2) + 2, i4 = "function" == typeof this.headerLength ? this.headerLength(e4, t4, s4) : this.headerLength, n3 = t4 + i4, r4 = s4 - i4;
    return { offset: t4, length: s4, headerLength: i4, start: n3, size: r4, end: n3 + r4 };
  }
  static parse(e4, t4 = {}) {
    return new this(e4, new R2({ [this.type]: t4 }), e4).parse();
  }
  normalizeInput(e4) {
    return e4 instanceof c3 ? e4 : new c3(e4);
  }
  constructor(t4, s4 = {}, i4) {
    e3(this, "errors", []), e3(this, "raw", /* @__PURE__ */ new Map()), e3(this, "handleError", ((e4) => {
      if (!this.options.silentErrors) throw e4;
      this.errors.push(e4.message);
    })), this.chunk = this.normalizeInput(t4), this.file = i4, this.type = this.constructor.type, this.globalOptions = this.options = s4, this.localOptions = s4[this.type], this.canTranslate = this.localOptions && this.localOptions.translate;
  }
  translate() {
    this.canTranslate && (this.translated = this.translateBlock(this.raw, this.type));
  }
  get output() {
    return this.translated ? this.translated : this.raw ? Object.fromEntries(this.raw) : void 0;
  }
  translateBlock(e4, t4) {
    let s4 = I2.get(t4), i4 = V3.get(t4), n3 = B4.get(t4), r4 = this.options[t4], a4 = r4.reviveValues && !!s4, h4 = r4.translateValues && !!i4, f5 = r4.translateKeys && !!n3, l4 = {};
    for (let [t5, r5] of e4) a4 && s4.has(t5) ? r5 = s4.get(t5)(r5) : h4 && i4.has(t5) && (r5 = this.translateValue(r5, i4.get(t5))), f5 && n3.has(t5) && (t5 = n3.get(t5) || t5), l4[t5] = r5;
    return l4;
  }
  translateValue(e4, t4) {
    return t4[e4] || t4.DEFAULT || e4;
  }
  assignToOutput(e4, t4) {
    this.assignObjectToOutput(e4, this.constructor.type, t4);
  }
  assignObjectToOutput(e4, t4, s4) {
    if (this.globalOptions.mergeOutput) return Object.assign(e4, s4);
    e4[t4] ? Object.assign(e4[t4], s4) : e4[t4] = s4;
  }
};
e3(J3, "headerLength", 4), e3(J3, "type", void 0), e3(J3, "multiSegment", false), e3(J3, "canHandle", (() => false));
function q4(e4) {
  return 192 === e4 || 194 === e4 || 196 === e4 || 219 === e4 || 221 === e4 || 218 === e4 || 254 === e4;
}
function Q3(e4) {
  return e4 >= 224 && e4 <= 239;
}
function Z(e4, t4, s4) {
  for (let [i4, n3] of y3) if (n3.canHandle(e4, t4, s4)) return i4;
}
var ee2 = class extends class {
  constructor(t4, s4, i4) {
    e3(this, "errors", []), e3(this, "ensureSegmentChunk", (async (e4) => {
      let t5 = e4.start, s5 = e4.size || 65536;
      if (this.file.chunked) if (this.file.available(t5, s5)) e4.chunk = this.file.subarray(t5, s5);
      else try {
        e4.chunk = await this.file.readChunk(t5, s5);
      } catch (t6) {
        l3(`Couldn't read segment: ${JSON.stringify(e4)}. ${t6.message}`);
      }
      else this.file.byteLength > t5 + s5 ? e4.chunk = this.file.subarray(t5, s5) : void 0 === e4.size ? e4.chunk = this.file.subarray(t5) : l3("Segment unreachable: " + JSON.stringify(e4));
      return e4.chunk;
    })), this.extendOptions && this.extendOptions(t4), this.options = t4, this.file = s4, this.parsers = i4;
  }
  injectSegment(e4, t4) {
    this.options[e4].enabled && this.createParser(e4, t4);
  }
  createParser(e4, t4) {
    let s4 = new (y3.get(e4))(t4, this.options, this.file);
    return this.parsers[e4] = s4;
  }
  createParsers(e4) {
    for (let t4 of e4) {
      let { type: e5, chunk: s4 } = t4, i4 = this.options[e5];
      if (i4 && i4.enabled) {
        let t5 = this.parsers[e5];
        t5 && t5.append || t5 || this.createParser(e5, s4);
      }
    }
  }
  async readSegments(e4) {
    let t4 = e4.map(this.ensureSegmentChunk);
    await Promise.all(t4);
  }
} {
  constructor(...t4) {
    super(...t4), e3(this, "appSegments", []), e3(this, "jpegSegments", []), e3(this, "unknownSegments", []);
  }
  static canHandle(e4, t4) {
    return 65496 === t4;
  }
  async parse() {
    await this.findAppSegments(), await this.readSegments(this.appSegments), this.mergeMultiSegments(), this.createParsers(this.mergedAppSegments || this.appSegments);
  }
  setupSegmentFinderArgs(e4) {
    true === e4 ? (this.findAll = true, this.wanted = new Set(y3.keyList())) : (e4 = void 0 === e4 ? y3.keyList().filter(((e5) => this.options[e5].enabled)) : e4.filter(((e5) => this.options[e5].enabled && y3.has(e5))), this.findAll = false, this.remaining = new Set(e4), this.wanted = new Set(e4)), this.unfinishedMultiSegment = false;
  }
  async findAppSegments(e4 = 0, t4) {
    this.setupSegmentFinderArgs(t4);
    let { file: s4, findAll: i4, wanted: n3, remaining: r4 } = this;
    if (!i4 && this.file.chunked && (i4 = Array.from(n3).some(((e5) => {
      let t5 = y3.get(e5), s5 = this.options[e5];
      return t5.multiSegment && s5.multiSegment;
    })), i4 && await this.file.readWhole()), e4 = this.findAppSegmentsInRange(e4, s4.byteLength), !this.options.onlyTiff && s4.chunked) {
      let t5 = false;
      for (; r4.size > 0 && !t5 && (s4.canReadNextChunk || this.unfinishedMultiSegment); ) {
        let { nextChunkOffset: i5 } = s4, n4 = this.appSegments.some(((e5) => !this.file.available(e5.offset || e5.start, e5.length || e5.size)));
        if (t5 = e4 > i5 && !n4 ? !await s4.readNextChunk(e4) : !await s4.readNextChunk(i5), void 0 === (e4 = this.findAppSegmentsInRange(e4, s4.byteLength))) return;
      }
    }
  }
  findAppSegmentsInRange(e4, t4) {
    t4 -= 2;
    let s4, i4, n3, r4, a4, h4, { file: f5, findAll: l4, wanted: o4, remaining: u5, options: d4 } = this;
    for (; e4 < t4; e4++) if (255 === f5.getUint8(e4)) {
      if (s4 = f5.getUint8(e4 + 1), Q3(s4)) {
        if (i4 = f5.getUint16(e4 + 2), n3 = Z(f5, e4, i4), n3 && o4.has(n3) && (r4 = y3.get(n3), a4 = r4.findPosition(f5, e4), h4 = d4[n3], a4.type = n3, this.appSegments.push(a4), !l4 && (r4.multiSegment && h4.multiSegment ? (this.unfinishedMultiSegment = a4.chunkNumber < a4.chunkCount, this.unfinishedMultiSegment || u5.delete(n3)) : u5.delete(n3), 0 === u5.size))) break;
        d4.recordUnknownSegments && (a4 = J3.findPosition(f5, e4), a4.marker = s4, this.unknownSegments.push(a4)), e4 += i4 + 1;
      } else if (q4(s4)) {
        if (i4 = f5.getUint16(e4 + 2), 218 === s4 && false !== d4.stopAfterSos) return;
        d4.recordJpegSegments && this.jpegSegments.push({ offset: e4, length: i4, marker: s4 }), e4 += i4 + 1;
      }
    }
    return e4;
  }
  mergeMultiSegments() {
    if (!this.appSegments.some(((e5) => e5.multiSegment))) return;
    let e4 = (function(e5, t4) {
      let s4, i4, n3, r4 = /* @__PURE__ */ new Map();
      for (let a4 = 0; a4 < e5.length; a4++) s4 = e5[a4], i4 = s4[t4], r4.has(i4) ? n3 = r4.get(i4) : r4.set(i4, n3 = []), n3.push(s4);
      return Array.from(r4);
    })(this.appSegments, "type");
    this.mergedAppSegments = e4.map((([e5, t4]) => {
      let s4 = y3.get(e5, this.options);
      if (s4.handleMultiSegments) {
        return { type: e5, chunk: s4.handleMultiSegments(t4) };
      }
      return t4[0];
    }));
  }
  getSegment(e4) {
    return this.appSegments.find(((t4) => t4.type === e4));
  }
  async getOrFindSegment(e4) {
    let t4 = this.getSegment(e4);
    return void 0 === t4 && (await this.findAppSegments(0, [e4]), t4 = this.getSegment(e4)), t4;
  }
};
e3(ee2, "type", "jpeg"), m3.set("jpeg", ee2);
var te = [void 0, 1, 1, 2, 4, 8, 1, 1, 2, 4, 8, 4, 8, 4];
var se = class extends J3 {
  parseHeader() {
    var e4 = this.chunk.getUint16();
    18761 === e4 ? this.le = true : 19789 === e4 && (this.le = false), this.chunk.le = this.le, this.headerParsed = true;
  }
  parseTags(e4, t4, s4 = /* @__PURE__ */ new Map()) {
    let { pick: i4, skip: n3 } = this.options[t4];
    i4 = new Set(i4);
    let r4 = i4.size > 0, a4 = 0 === n3.size, h4 = this.chunk.getUint16(e4);
    e4 += 2;
    for (let f5 = 0; f5 < h4; f5++) {
      let h5 = this.chunk.getUint16(e4);
      if (r4) {
        if (i4.has(h5) && (s4.set(h5, this.parseTag(e4, h5, t4)), i4.delete(h5), 0 === i4.size)) break;
      } else !a4 && n3.has(h5) || s4.set(h5, this.parseTag(e4, h5, t4));
      e4 += 12;
    }
    return s4;
  }
  parseTag(e4, t4, s4) {
    let { chunk: i4 } = this, n3 = i4.getUint16(e4 + 2), r4 = i4.getUint32(e4 + 4), a4 = te[n3];
    if (a4 * r4 <= 4 ? e4 += 8 : e4 = i4.getUint32(e4 + 8), (n3 < 1 || n3 > 13) && l3(`Invalid TIFF value type. block: ${s4.toUpperCase()}, tag: ${t4.toString(16)}, type: ${n3}, offset ${e4}`), e4 > i4.byteLength && l3(`Invalid TIFF value offset. block: ${s4.toUpperCase()}, tag: ${t4.toString(16)}, type: ${n3}, offset ${e4} is outside of chunk size ${i4.byteLength}`), 1 === n3) return i4.getUint8Array(e4, r4);
    if (2 === n3) return "" === (h4 = (function(e5) {
      for (; e5.endsWith("\0"); ) e5 = e5.slice(0, -1);
      return e5;
    })(h4 = i4.getString(e4, r4)).trim()) ? void 0 : h4;
    var h4;
    if (7 === n3) return i4.getUint8Array(e4, r4);
    if (1 === r4) return this.parseTagValue(n3, e4);
    {
      let t5 = new ((function(e5) {
        switch (e5) {
          case 1:
            return Uint8Array;
          case 3:
            return Uint16Array;
          case 4:
            return Uint32Array;
          case 5:
            return Array;
          case 6:
            return Int8Array;
          case 8:
            return Int16Array;
          case 9:
            return Int32Array;
          case 10:
            return Array;
          case 11:
            return Float32Array;
          case 12:
            return Float64Array;
          default:
            return Array;
        }
      })(n3))(r4), s5 = a4;
      for (let i5 = 0; i5 < r4; i5++) t5[i5] = this.parseTagValue(n3, e4), e4 += s5;
      return t5;
    }
  }
  parseTagValue(e4, t4) {
    let { chunk: s4 } = this;
    switch (e4) {
      case 1:
        return s4.getUint8(t4);
      case 3:
        return s4.getUint16(t4);
      case 4:
        return s4.getUint32(t4);
      case 5:
        return s4.getUint32(t4) / s4.getUint32(t4 + 4);
      case 6:
        return s4.getInt8(t4);
      case 8:
        return s4.getInt16(t4);
      case 9:
        return s4.getInt32(t4);
      case 10:
        return s4.getInt32(t4) / s4.getInt32(t4 + 4);
      case 11:
        return s4.getFloat(t4);
      case 12:
        return s4.getDouble(t4);
      case 13:
        return s4.getUint32(t4);
      default:
        l3(`Invalid tiff type ${e4}`);
    }
  }
};
var ie = class extends se {
  static canHandle(e4, t4) {
    return 225 === e4.getUint8(t4 + 1) && 1165519206 === e4.getUint32(t4 + 4) && 0 === e4.getUint16(t4 + 8);
  }
  async parse() {
    this.parseHeader();
    let { options: e4 } = this;
    return e4.ifd0.enabled && await this.parseIfd0Block(), e4.exif.enabled && await this.safeParse("parseExifBlock"), e4.gps.enabled && await this.safeParse("parseGpsBlock"), e4.interop.enabled && await this.safeParse("parseInteropBlock"), e4.ifd1.enabled && await this.safeParse("parseThumbnailBlock"), this.createOutput();
  }
  safeParse(e4) {
    let t4 = this[e4]();
    return void 0 !== t4.catch && (t4 = t4.catch(this.handleError)), t4;
  }
  findIfd0Offset() {
    void 0 === this.ifd0Offset && (this.ifd0Offset = this.chunk.getUint32(4));
  }
  findIfd1Offset() {
    if (void 0 === this.ifd1Offset) {
      this.findIfd0Offset();
      let e4 = this.chunk.getUint16(this.ifd0Offset), t4 = this.ifd0Offset + 2 + 12 * e4;
      this.ifd1Offset = this.chunk.getUint32(t4);
    }
  }
  parseBlock(e4, t4) {
    let s4 = /* @__PURE__ */ new Map();
    return this[t4] = s4, this.parseTags(e4, t4, s4), s4;
  }
  async parseIfd0Block() {
    if (this.ifd0) return;
    let { file: e4 } = this;
    this.findIfd0Offset(), this.ifd0Offset < 8 && l3("Malformed EXIF data"), !e4.chunked && this.ifd0Offset > e4.byteLength && l3(`IFD0 offset points to outside of file.
this.ifd0Offset: ${this.ifd0Offset}, file.byteLength: ${e4.byteLength}`), e4.tiff && await e4.ensureChunk(this.ifd0Offset, o3(this.options));
    let t4 = this.parseBlock(this.ifd0Offset, "ifd0");
    return 0 !== t4.size ? (this.exifOffset = t4.get(34665), this.interopOffset = t4.get(40965), this.gpsOffset = t4.get(34853), this.xmp = t4.get(700), this.iptc = t4.get(33723), this.icc = t4.get(34675), this.options.sanitize && (t4.delete(34665), t4.delete(40965), t4.delete(34853), t4.delete(700), t4.delete(33723), t4.delete(34675)), t4) : void 0;
  }
  async parseExifBlock() {
    if (this.exif) return;
    if (this.ifd0 || await this.parseIfd0Block(), void 0 === this.exifOffset) return;
    this.file.tiff && await this.file.ensureChunk(this.exifOffset, o3(this.options));
    let e4 = this.parseBlock(this.exifOffset, "exif");
    return this.interopOffset || (this.interopOffset = e4.get(40965)), this.makerNote = e4.get(37500), this.userComment = e4.get(37510), this.options.sanitize && (e4.delete(40965), e4.delete(37500), e4.delete(37510)), this.unpack(e4, 41728), this.unpack(e4, 41729), e4;
  }
  unpack(e4, t4) {
    let s4 = e4.get(t4);
    s4 && 1 === s4.length && e4.set(t4, s4[0]);
  }
  async parseGpsBlock() {
    if (this.gps) return;
    if (this.ifd0 || await this.parseIfd0Block(), void 0 === this.gpsOffset) return;
    let e4 = this.parseBlock(this.gpsOffset, "gps");
    return e4 && e4.has(2) && e4.has(4) && (e4.set("latitude", ne(...e4.get(2), e4.get(1))), e4.set("longitude", ne(...e4.get(4), e4.get(3)))), e4;
  }
  async parseInteropBlock() {
    if (!this.interop && (this.ifd0 || await this.parseIfd0Block(), void 0 !== this.interopOffset || this.exif || await this.parseExifBlock(), void 0 !== this.interopOffset)) return this.parseBlock(this.interopOffset, "interop");
  }
  async parseThumbnailBlock(e4 = false) {
    if (!this.ifd1 && !this.ifd1Parsed && (!this.options.mergeOutput || e4)) return this.findIfd1Offset(), this.ifd1Offset > 0 && (this.parseBlock(this.ifd1Offset, "ifd1"), this.ifd1Parsed = true), this.ifd1;
  }
  async extractThumbnail() {
    if (this.headerParsed || this.parseHeader(), this.ifd1Parsed || await this.parseThumbnailBlock(true), void 0 === this.ifd1) return;
    let e4 = this.ifd1.get(513), t4 = this.ifd1.get(514);
    return this.chunk.getUint8Array(e4, t4);
  }
  get image() {
    return this.ifd0;
  }
  get thumbnail() {
    return this.ifd1;
  }
  createOutput() {
    let e4, t4, s4, i4 = {};
    for (t4 of P4) if (e4 = this[t4], !f4(e4)) if (s4 = this.canTranslate ? this.translateBlock(e4, t4) : Object.fromEntries(e4), this.options.mergeOutput) {
      if ("ifd1" === t4) continue;
      Object.assign(i4, s4);
    } else i4[t4] = s4;
    return this.makerNote && (i4.makerNote = this.makerNote), this.userComment && (i4.userComment = this.userComment), i4;
  }
  assignToOutput(e4, t4) {
    if (this.globalOptions.mergeOutput) Object.assign(e4, t4);
    else for (let [s4, i4] of Object.entries(t4)) this.assignObjectToOutput(e4, s4, i4);
  }
};
function ne(e4, t4, s4, i4) {
  var n3 = e4 + t4 / 60 + s4 / 3600;
  return "S" !== i4 && "W" !== i4 || (n3 *= -1), n3;
}
e3(ie, "type", "tiff"), e3(ie, "headerLength", 10), y3.set("tiff", ie);
var re = Object.freeze({ __proto__: null, default: G3, Exifr: H3, fileParsers: m3, segmentParsers: y3, fileReaders: b2, tagKeys: B4, tagValues: V3, tagRevivers: I2, createDictionary: x3, extendDictionary: C3, fetchUrlAsArrayBuffer: S2, readBlobAsArrayBuffer: A4, chunkedProps: L2, otherSegments: T4, segments: z3, tiffBlocks: P4, segmentsAndBlocks: F3, tiffExtractables: j4, inheritables: E3, allFormatters: M3, Options: R2, parse: Y });
var ae = { ifd0: false, ifd1: false, exif: false, gps: false, interop: false, sanitize: false, reviveValues: true, translateKeys: false, translateValues: false, mergeOutput: false };
var he = Object.assign({}, ae, { firstChunkSize: 4e4, gps: [1, 2, 3, 4] });
var le = Object.assign({}, ae, { tiff: false, ifd1: true, mergeOutput: false });
var de = Object.assign({}, ae, { firstChunkSize: 4e4, ifd0: [274] });
async function ce(e4) {
  let t4 = new H3(de);
  await t4.read(e4);
  let s4 = await t4.parse();
  if (s4 && s4.ifd0) return s4.ifd0[274];
}
var pe = Object.freeze({ 1: { dimensionSwapped: false, scaleX: 1, scaleY: 1, deg: 0, rad: 0 }, 2: { dimensionSwapped: false, scaleX: -1, scaleY: 1, deg: 0, rad: 0 }, 3: { dimensionSwapped: false, scaleX: 1, scaleY: 1, deg: 180, rad: 180 * Math.PI / 180 }, 4: { dimensionSwapped: false, scaleX: -1, scaleY: 1, deg: 180, rad: 180 * Math.PI / 180 }, 5: { dimensionSwapped: true, scaleX: 1, scaleY: -1, deg: 90, rad: 90 * Math.PI / 180 }, 6: { dimensionSwapped: true, scaleX: 1, scaleY: 1, deg: 90, rad: 90 * Math.PI / 180 }, 7: { dimensionSwapped: true, scaleX: 1, scaleY: -1, deg: 270, rad: 270 * Math.PI / 180 }, 8: { dimensionSwapped: true, scaleX: 1, scaleY: 1, deg: 270, rad: 270 * Math.PI / 180 } });
var ge = true;
var me = true;
if ("object" == typeof navigator) {
  let e4 = navigator.userAgent;
  if (e4.includes("iPad") || e4.includes("iPhone")) {
    let t4 = e4.match(/OS (\d+)_(\d+)/);
    if (t4) {
      let [, e5, s4] = t4, i4 = Number(e5) + 0.1 * Number(s4);
      ge = i4 < 13.4, me = false;
    }
  } else if (e4.includes("OS X 10")) {
    let [, t4] = e4.match(/OS X 10[_.](\d+)/);
    ge = me = Number(t4) < 15;
  }
  if (e4.includes("Chrome/")) {
    let [, t4] = e4.match(/Chrome\/(\d+)/);
    ge = me = Number(t4) < 81;
  } else if (e4.includes("Firefox/")) {
    let [, t4] = e4.match(/Firefox\/(\d+)/);
    ge = me = Number(t4) < 77;
  }
}
async function ye(e4) {
  let t4 = await ce(e4);
  return Object.assign({ canvas: ge, css: me }, pe[t4]);
}
var be = class extends c3 {
  constructor(...t4) {
    super(...t4), e3(this, "ranges", new we()), 0 !== this.byteLength && this.ranges.add(0, this.byteLength);
  }
  _tryExtend(e4, t4, s4) {
    if (0 === e4 && 0 === this.byteLength && s4) {
      let e5 = new DataView(s4.buffer || s4, s4.byteOffset, s4.byteLength);
      this._swapDataView(e5);
    } else {
      let s5 = e4 + t4;
      if (s5 > this.byteLength) {
        let { dataView: e5 } = this._extend(s5);
        this._swapDataView(e5);
      }
    }
  }
  _extend(e4) {
    let t4;
    t4 = a3 ? r3.allocUnsafe(e4) : new Uint8Array(e4);
    let s4 = new DataView(t4.buffer, t4.byteOffset, t4.byteLength);
    return t4.set(new Uint8Array(this.buffer, this.byteOffset, this.byteLength), 0), { uintView: t4, dataView: s4 };
  }
  subarray(e4, t4, s4 = false) {
    return t4 = t4 || this._lengthToEnd(e4), s4 && this._tryExtend(e4, t4), this.ranges.add(e4, t4), super.subarray(e4, t4);
  }
  set(e4, t4, s4 = false) {
    s4 && this._tryExtend(t4, e4.byteLength, e4);
    let i4 = super.set(e4, t4);
    return this.ranges.add(t4, i4.byteLength), i4;
  }
  async ensureChunk(e4, t4) {
    this.chunked && (this.ranges.available(e4, t4) || await this.readChunk(e4, t4));
  }
  available(e4, t4) {
    return this.ranges.available(e4, t4);
  }
};
var we = class {
  constructor() {
    e3(this, "list", []);
  }
  get length() {
    return this.list.length;
  }
  add(e4, t4, s4 = 0) {
    let i4 = e4 + t4, n3 = this.list.filter(((t5) => ke(e4, t5.offset, i4) || ke(e4, t5.end, i4)));
    if (n3.length > 0) {
      e4 = Math.min(e4, ...n3.map(((e5) => e5.offset))), i4 = Math.max(i4, ...n3.map(((e5) => e5.end))), t4 = i4 - e4;
      let s5 = n3.shift();
      s5.offset = e4, s5.length = t4, s5.end = i4, this.list = this.list.filter(((e5) => !n3.includes(e5)));
    } else this.list.push({ offset: e4, length: t4, end: i4 });
  }
  available(e4, t4) {
    let s4 = e4 + t4;
    return this.list.some(((t5) => t5.offset <= e4 && s4 <= t5.end));
  }
};
function ke(e4, t4, s4) {
  return e4 <= t4 && t4 <= s4;
}
var Oe = class extends be {
  constructor(t4, s4) {
    super(0), e3(this, "chunksRead", 0), this.input = t4, this.options = s4;
  }
  async readWhole() {
    this.chunked = false, await this.readChunk(this.nextChunkOffset);
  }
  async readChunked() {
    this.chunked = true, await this.readChunk(0, this.options.firstChunkSize);
  }
  async readNextChunk(e4 = this.nextChunkOffset) {
    if (this.fullyRead) return this.chunksRead++, false;
    let t4 = this.options.chunkSize, s4 = await this.readChunk(e4, t4);
    return !!s4 && s4.byteLength === t4;
  }
  async readChunk(e4, t4) {
    if (this.chunksRead++, 0 !== (t4 = this.safeWrapAddress(e4, t4))) return this._readChunk(e4, t4);
  }
  safeWrapAddress(e4, t4) {
    return void 0 !== this.size && e4 + t4 > this.size ? Math.max(0, this.size - e4) : t4;
  }
  get nextChunkOffset() {
    if (0 !== this.ranges.list.length) return this.ranges.list[0].length;
  }
  get canReadNextChunk() {
    return this.chunksRead < this.options.chunkLimit;
  }
  get fullyRead() {
    return void 0 !== this.size && this.nextChunkOffset === this.size;
  }
  read() {
    return this.options.chunked ? this.readChunked() : this.readWhole();
  }
  close() {
  }
};
b2.set("blob", class extends Oe {
  async readWhole() {
    this.chunked = false;
    let e4 = await A4(this.input);
    this._swapArrayBuffer(e4);
  }
  readChunked() {
    return this.chunked = true, this.size = this.input.size, super.readChunked();
  }
  async _readChunk(e4, t4) {
    let s4 = t4 ? e4 + t4 : void 0, i4 = this.input.slice(e4, s4), n3 = await A4(i4);
    return this.set(n3, e4, true);
  }
});

// node_modules/@uppy/thumbnail-generator/package.json
var package_default6 = {
  name: "@uppy/thumbnail-generator",
  description: "Uppy plugin that generates small previews of images to show on your upload UI.",
  version: "4.2.3",
  license: "MIT",
  main: "lib/index.js",
  type: "module",
  scripts: {
    build: "tsc --build tsconfig.build.json",
    typecheck: "tsc --build",
    test: "vitest run --environment=jsdom --silent='passed-only'"
  },
  keywords: [
    "file uploader",
    "uppy",
    "uppy-plugin",
    "thumbnail",
    "preview",
    "resize"
  ],
  homepage: "https://uppy.io",
  bugs: {
    url: "https://github.com/transloadit/uppy/issues"
  },
  repository: {
    type: "git",
    url: "git+https://github.com/transloadit/uppy.git"
  },
  files: [
    "src",
    "lib",
    "dist",
    "CHANGELOG.md"
  ],
  dependencies: {
    "@uppy/utils": "^6.2.2",
    exifr: "^7.0.0"
  },
  devDependencies: {
    jsdom: "^26.1.0",
    "namespace-emitter": "2.0.1",
    typescript: "^5.8.3",
    vitest: "^3.2.4"
  },
  peerDependencies: {
    "@uppy/core": "^4.5.3"
  }
};

// node_modules/@uppy/thumbnail-generator/lib/locale.js
var locale_default3 = {
  strings: {
    generatingThumbnails: "Generating thumbnails..."
  }
};

// node_modules/@uppy/thumbnail-generator/lib/index.js
function canvasToBlob(canvas, type, quality) {
  try {
    canvas.getContext("2d").getImageData(0, 0, 1, 1);
  } catch (err) {
    if (err.code === 18) {
      return Promise.reject(new Error("cannot read image, probably an svg with external resources"));
    }
  }
  if (canvas.toBlob) {
    return new Promise((resolve) => {
      canvas.toBlob(resolve, type, quality);
    }).then((blob) => {
      if (blob === null) {
        throw new Error("cannot read image, probably an svg with external resources");
      }
      return blob;
    });
  }
  return Promise.resolve().then(() => {
    return dataURItoBlob_default(canvas.toDataURL(type, quality), {});
  }).then((blob) => {
    if (blob === null) {
      throw new Error("could not extract blob, probably an old browser");
    }
    return blob;
  });
}
function rotateImage(image, translate) {
  let w4 = image.width;
  let h4 = image.height;
  if (translate.deg === 90 || translate.deg === 270) {
    w4 = image.height;
    h4 = image.width;
  }
  const canvas = document.createElement("canvas");
  canvas.width = w4;
  canvas.height = h4;
  const context = canvas.getContext("2d");
  context.translate(w4 / 2, h4 / 2);
  if (translate.canvas) {
    context.rotate(translate.rad);
    context.scale(translate.scaleX, translate.scaleY);
  }
  context.drawImage(image, -image.width / 2, -image.height / 2, image.width, image.height);
  return canvas;
}
function protect(image) {
  const ratio = image.width / image.height;
  const maxSquare = 5e6;
  const maxSize = 4096;
  let maxW = Math.floor(Math.sqrt(maxSquare * ratio));
  let maxH = Math.floor(maxSquare / Math.sqrt(maxSquare * ratio));
  if (maxW > maxSize) {
    maxW = maxSize;
    maxH = Math.round(maxW / ratio);
  }
  if (maxH > maxSize) {
    maxH = maxSize;
    maxW = Math.round(ratio * maxH);
  }
  if (image.width > maxW) {
    const canvas = document.createElement("canvas");
    canvas.width = maxW;
    canvas.height = maxH;
    canvas.getContext("2d").drawImage(image, 0, 0, maxW, maxH);
    return canvas;
  }
  return image;
}
var defaultOptions4 = {
  thumbnailWidth: null,
  thumbnailHeight: null,
  thumbnailType: "image/jpeg",
  waitForThumbnailsBeforeUpload: false,
  lazy: false
};
var ThumbnailGenerator = class extends UIPlugin_default {
  constructor(uppy, opts) {
    super(uppy, { ...defaultOptions4, ...opts });
    __publicField(this, "queue");
    __publicField(this, "queueProcessing");
    __publicField(this, "defaultThumbnailDimension");
    __publicField(this, "thumbnailType");
    __publicField(this, "onFileAdded", (file) => {
      if (!file.preview && file.data && isPreviewSupported(file.type) && !file.isRemote) {
        this.addToQueue(file.id);
      }
    });
    /**
     * Cancel a lazy request for a thumbnail if the thumbnail has not yet been generated.
     */
    __publicField(this, "onCancelRequest", (file) => {
      const index = this.queue.indexOf(file.id);
      if (index !== -1) {
        this.queue.splice(index, 1);
      }
    });
    /**
     * Clean up the thumbnail for a file. Cancel lazy requests and free the thumbnail URL.
     */
    __publicField(this, "onFileRemoved", (file) => {
      const index = this.queue.indexOf(file.id);
      if (index !== -1) {
        this.queue.splice(index, 1);
      }
      if (file.preview && isObjectURL(file.preview)) {
        URL.revokeObjectURL(file.preview);
      }
    });
    __publicField(this, "onRestored", () => {
      const restoredFiles = this.uppy.getFiles().filter((file) => file.isRestored);
      restoredFiles.forEach((file) => {
        if (!file.preview || isObjectURL(file.preview)) {
          this.addToQueue(file.id);
        }
      });
    });
    __publicField(this, "onAllFilesRemoved", () => {
      this.queue = [];
    });
    __publicField(this, "waitUntilAllProcessed", (fileIDs) => {
      fileIDs.forEach((fileID) => {
        const file = this.uppy.getFile(fileID);
        this.uppy.emit("preprocess-progress", file, {
          mode: "indeterminate",
          message: this.i18n("generatingThumbnails")
        });
      });
      const emitPreprocessCompleteForAll = () => {
        fileIDs.forEach((fileID) => {
          const file = this.uppy.getFile(fileID);
          this.uppy.emit("preprocess-complete", file);
        });
      };
      return new Promise((resolve) => {
        if (this.queueProcessing) {
          this.uppy.once("thumbnail:all-generated", () => {
            emitPreprocessCompleteForAll();
            resolve();
          });
        } else {
          emitPreprocessCompleteForAll();
          resolve();
        }
      });
    });
    this.type = "modifier";
    this.id = this.opts.id || "ThumbnailGenerator";
    this.title = "Thumbnail Generator";
    this.queue = [];
    this.queueProcessing = false;
    this.defaultThumbnailDimension = 200;
    this.thumbnailType = this.opts.thumbnailType;
    this.defaultLocale = locale_default3;
    this.i18nInit();
    if (this.opts.lazy && this.opts.waitForThumbnailsBeforeUpload) {
      throw new Error("ThumbnailGenerator: The `lazy` and `waitForThumbnailsBeforeUpload` options are mutually exclusive. Please ensure at most one of them is set to `true`.");
    }
  }
  createThumbnail(file, targetWidth, targetHeight) {
    const originalUrl = URL.createObjectURL(file.data);
    const onload = new Promise((resolve, reject) => {
      const image = new Image();
      image.src = originalUrl;
      image.addEventListener("load", () => {
        URL.revokeObjectURL(originalUrl);
        resolve(image);
      });
      image.addEventListener("error", (event) => {
        URL.revokeObjectURL(originalUrl);
        reject(event.error || new Error("Could not create thumbnail"));
      });
    });
    const orientationPromise = ye(file.data).catch(() => 1);
    return Promise.all([onload, orientationPromise]).then(([image, orientation]) => {
      const dimensions = this.getProportionalDimensions(image, targetWidth, targetHeight, orientation.deg);
      const rotatedImage = rotateImage(image, orientation);
      const resizedImage = this.resizeImage(rotatedImage, dimensions.width, dimensions.height);
      return canvasToBlob(resizedImage, this.thumbnailType, 80);
    }).then((blob) => {
      return URL.createObjectURL(blob);
    });
  }
  /**
   * Get the new calculated dimensions for the given image and a target width
   * or height. If both width and height are given, only width is taken into
   * account. If neither width nor height are given, the default dimension
   * is used.
   */
  getProportionalDimensions(img, width, height, deg) {
    let aspect = img.width / img.height;
    if (deg === 90 || deg === 270) {
      aspect = img.height / img.width;
    }
    if (width != null) {
      let targetWidth = width;
      if (img.width < width)
        targetWidth = img.width;
      return {
        width: targetWidth,
        height: Math.round(targetWidth / aspect)
      };
    }
    if (height != null) {
      let targetHeight = height;
      if (img.height < height)
        targetHeight = img.height;
      return {
        width: Math.round(targetHeight * aspect),
        height: targetHeight
      };
    }
    return {
      width: this.defaultThumbnailDimension,
      height: Math.round(this.defaultThumbnailDimension / aspect)
    };
  }
  /**
   * Resize an image to the target `width` and `height`.
   *
   * Returns a Canvas with the resized image on it.
   */
  resizeImage(image, targetWidth, targetHeight) {
    let img = protect(image);
    let steps = Math.ceil(Math.log2(img.width / targetWidth));
    if (steps < 1) {
      steps = 1;
    }
    let sW = targetWidth * 2 ** (steps - 1);
    let sH = targetHeight * 2 ** (steps - 1);
    const x4 = 2;
    while (steps--) {
      const canvas = document.createElement("canvas");
      canvas.width = sW;
      canvas.height = sH;
      canvas.getContext("2d").drawImage(img, 0, 0, sW, sH);
      img = canvas;
      sW = Math.round(sW / x4);
      sH = Math.round(sH / x4);
    }
    return img;
  }
  /**
   * Set the preview URL for a file.
   */
  setPreviewURL(fileID, preview) {
    this.uppy.setFileState(fileID, { preview });
  }
  addToQueue(fileID) {
    this.queue.push(fileID);
    if (this.queueProcessing === false) {
      this.processQueue();
    }
  }
  processQueue() {
    this.queueProcessing = true;
    if (this.queue.length > 0) {
      const current = this.uppy.getFile(this.queue.shift());
      if (!current) {
        this.uppy.log("[ThumbnailGenerator] file was removed before a thumbnail could be generated, but not removed from the queue. This is probably a bug", "error");
        return Promise.resolve();
      }
      return this.requestThumbnail(current).catch(() => {
      }).then(() => this.processQueue());
    }
    this.queueProcessing = false;
    this.uppy.log("[ThumbnailGenerator] Emptied thumbnail queue");
    this.uppy.emit("thumbnail:all-generated");
    return Promise.resolve();
  }
  requestThumbnail(file) {
    if (isPreviewSupported(file.type) && !file.isRemote) {
      return this.createThumbnail(file, this.opts.thumbnailWidth, this.opts.thumbnailHeight).then((preview) => {
        this.setPreviewURL(file.id, preview);
        this.uppy.log(`[ThumbnailGenerator] Generated thumbnail for ${file.id}`);
        this.uppy.emit("thumbnail:generated", this.uppy.getFile(file.id), preview);
      }).catch((err) => {
        this.uppy.log(`[ThumbnailGenerator] Failed thumbnail for ${file.id}:`, "warning");
        this.uppy.log(err, "warning");
        this.uppy.emit("thumbnail:error", this.uppy.getFile(file.id), err);
      });
    }
    return Promise.resolve();
  }
  install() {
    this.uppy.on("file-removed", this.onFileRemoved);
    this.uppy.on("cancel-all", this.onAllFilesRemoved);
    if (this.opts.lazy) {
      this.uppy.on("thumbnail:request", this.onFileAdded);
      this.uppy.on("thumbnail:cancel", this.onCancelRequest);
    } else {
      this.uppy.on("thumbnail:request", this.onFileAdded);
      this.uppy.on("file-added", this.onFileAdded);
      this.uppy.on("restored", this.onRestored);
    }
    if (this.opts.waitForThumbnailsBeforeUpload) {
      this.uppy.addPreProcessor(this.waitUntilAllProcessed);
    }
  }
  uninstall() {
    this.uppy.off("file-removed", this.onFileRemoved);
    this.uppy.off("cancel-all", this.onAllFilesRemoved);
    if (this.opts.lazy) {
      this.uppy.off("thumbnail:request", this.onFileAdded);
      this.uppy.off("thumbnail:cancel", this.onCancelRequest);
    } else {
      this.uppy.off("thumbnail:request", this.onFileAdded);
      this.uppy.off("file-added", this.onFileAdded);
      this.uppy.off("restored", this.onRestored);
    }
    if (this.opts.waitForThumbnailsBeforeUpload) {
      this.uppy.removePreProcessor(this.waitUntilAllProcessed);
    }
  }
};
__publicField(ThumbnailGenerator, "VERSION", package_default6.version);

// node_modules/@uppy/utils/lib/findAllDOMElements.js
function findAllDOMElements(element) {
  if (typeof element === "string") {
    const elements = document.querySelectorAll(element);
    return elements.length === 0 ? null : Array.from(elements);
  }
  if (typeof element === "object" && isDOMElement(element)) {
    return [element];
  }
  return null;
}
var findAllDOMElements_default = findAllDOMElements;

// node_modules/@uppy/utils/lib/toArray.js
var toArray_default = Array.from;

// node_modules/@uppy/utils/lib/getDroppedFiles/utils/fallbackApi.js
function fallbackApi(dataTransfer) {
  const files = toArray_default(dataTransfer.files);
  return Promise.resolve(files);
}

// node_modules/@uppy/utils/lib/getDroppedFiles/utils/webkitGetAsEntryApi/getFilesAndDirectoriesFromDirectory.js
function getFilesAndDirectoriesFromDirectory(directoryReader, oldEntries, logDropError, { onSuccess }) {
  directoryReader.readEntries(
    (entries) => {
      const newEntries = [...oldEntries, ...entries];
      if (entries.length) {
        queueMicrotask(() => {
          getFilesAndDirectoriesFromDirectory(directoryReader, newEntries, logDropError, { onSuccess });
        });
      } else {
        onSuccess(newEntries);
      }
    },
    // Make sure we resolve on error anyway, it's fine if only one directory couldn't be parsed!
    (error) => {
      logDropError(error);
      onSuccess(oldEntries);
    }
  );
}

// node_modules/@uppy/utils/lib/getDroppedFiles/utils/webkitGetAsEntryApi/index.js
function getAsFileSystemHandleFromEntry(entry, logDropError) {
  if (entry == null)
    return entry;
  return {
    kind: entry.isFile ? "file" : entry.isDirectory ? "directory" : void 0,
    name: entry.name,
    getFile() {
      return new Promise((resolve, reject) => entry.file(resolve, reject));
    },
    async *values() {
      const directoryReader = entry.createReader();
      const entries = await new Promise((resolve) => {
        getFilesAndDirectoriesFromDirectory(directoryReader, [], logDropError, {
          onSuccess: (dirEntries) => resolve(dirEntries.map((file) => getAsFileSystemHandleFromEntry(file, logDropError)))
        });
      });
      yield* entries;
    },
    isSameEntry: void 0
  };
}
async function* createPromiseToAddFileOrParseDirectory(entry, relativePath, lastResortFile = void 0) {
  const getNextRelativePath = () => `${relativePath}/${entry.name}`;
  if (entry.kind === "file") {
    const file = await entry.getFile();
    if (file != null) {
      ;
      file.relativePath = relativePath ? getNextRelativePath() : null;
      yield file;
    } else if (lastResortFile != null)
      yield lastResortFile;
  } else if (entry.kind === "directory") {
    for await (const handle of entry.values()) {
      yield* createPromiseToAddFileOrParseDirectory(handle, relativePath ? getNextRelativePath() : entry.name);
    }
  } else if (lastResortFile != null)
    yield lastResortFile;
}
async function* getFilesFromDataTransfer(dataTransfer, logDropError) {
  const fileSystemHandles = await Promise.all(Array.from(dataTransfer.items, async (item) => {
    let fileSystemHandle;
    const getAsEntry = () => typeof item.getAsEntry === "function" ? item.getAsEntry() : item.webkitGetAsEntry();
    fileSystemHandle ?? (fileSystemHandle = getAsFileSystemHandleFromEntry(getAsEntry(), logDropError));
    return {
      fileSystemHandle,
      lastResortFile: item.getAsFile()
      // can be used as a fallback in case other methods fail
    };
  }));
  for (const { lastResortFile, fileSystemHandle } of fileSystemHandles) {
    if (fileSystemHandle != null) {
      try {
        yield* createPromiseToAddFileOrParseDirectory(fileSystemHandle, "", lastResortFile);
      } catch (err) {
        if (lastResortFile != null) {
          yield lastResortFile;
        } else {
          logDropError(err);
        }
      }
    } else if (lastResortFile != null)
      yield lastResortFile;
  }
}

// node_modules/@uppy/utils/lib/getDroppedFiles/index.js
async function getDroppedFiles(dataTransfer, options) {
  const logDropError = options?.logDropError ?? Function.prototype;
  try {
    const accumulator = [];
    for await (const file of getFilesFromDataTransfer(dataTransfer, logDropError)) {
      accumulator.push(file);
    }
    return accumulator;
  } catch {
    return fallbackApi(dataTransfer);
  }
}

// node_modules/@uppy/dashboard/node_modules/nanoid/non-secure/index.js
var urlAlphabet3 = "useandom-26T198340PX75pxJACKVERYMINDBUSHWOLF_GQZbfghjklqvwyzrict";
var nanoid3 = (size = 21) => {
  let id = "";
  let i4 = size | 0;
  while (i4-- > 0) {
    id += urlAlphabet3[Math.random() * 64 | 0];
  }
  return id;
};

// node_modules/@uppy/dashboard/package.json
var package_default7 = {
  name: "@uppy/dashboard",
  description: "Universal UI plugin for Uppy.",
  version: "4.4.3",
  license: "MIT",
  main: "lib/index.js",
  style: "dist/style.min.css",
  type: "module",
  scripts: {
    build: "tsc --build tsconfig.build.json",
    "build:css": "sass --load-path=../../ src/style.scss dist/style.css && postcss dist/style.css -u cssnano -o dist/style.min.css",
    typecheck: "tsc --build",
    test: "vitest run --silent='passed-only'",
    "test:e2e": "vitest watch --project browser --browser.headless false"
  },
  keywords: [
    "file uploader",
    "uppy",
    "uppy-plugin",
    "dashboard",
    "ui"
  ],
  homepage: "https://uppy.io",
  bugs: {
    url: "https://github.com/transloadit/uppy/issues"
  },
  repository: {
    type: "git",
    url: "git+https://github.com/transloadit/uppy.git"
  },
  files: [
    "src",
    "lib",
    "dist",
    "CHANGELOG.md"
  ],
  dependencies: {
    "@transloadit/prettier-bytes": "^0.3.4",
    "@uppy/informer": "^4.3.2",
    "@uppy/provider-views": "^4.5.2",
    "@uppy/status-bar": "^4.2.3",
    "@uppy/thumbnail-generator": "^4.2.2",
    "@uppy/utils": "^6.2.2",
    classnames: "^2.2.6",
    lodash: "^4.17.21",
    nanoid: "^5.0.9",
    preact: "^10.5.13",
    "shallow-equal": "^3.0.0"
  },
  devDependencies: {
    "@uppy/core": "^4.5.2",
    "@uppy/google-drive": "^4.4.2",
    "@uppy/status-bar": "^4.2.3",
    "@uppy/url": "^4.3.2",
    "@uppy/webcam": "^4.3.2",
    "@vitest/browser": "^3.2.4",
    cssnano: "^7.0.7",
    jsdom: "^26.1.0",
    postcss: "^8.5.6",
    "postcss-cli": "^11.0.1",
    "resize-observer-polyfill": "^1.5.0",
    sass: "^1.89.2",
    typescript: "^5.8.3",
    vitest: "^3.2.4"
  },
  peerDependencies: {
    "@uppy/core": "^4.5.2"
  }
};

// node_modules/@uppy/utils/lib/isDragDropSupported.js
function isDragDropSupported() {
  const div = document.body;
  if (!("draggable" in div) || !("ondragstart" in div && "ondrop" in div)) {
    return false;
  }
  if (!("FormData" in window)) {
    return false;
  }
  if (!("FileReader" in window)) {
    return false;
  }
  return true;
}

// node_modules/@uppy/dashboard/lib/components/Dashboard.js
var import_classnames14 = __toESM(require_classnames(), 1);

// node_modules/@uppy/dashboard/lib/components/AddFiles.js
var AddFiles = class extends C {
  constructor() {
    super(...arguments);
    __publicField(this, "fileInput", null);
    __publicField(this, "folderInput", null);
    __publicField(this, "mobilePhotoFileInput", null);
    __publicField(this, "mobileVideoFileInput", null);
    __publicField(this, "triggerFileInputClick", () => {
      this.fileInput?.click();
    });
    __publicField(this, "triggerFolderInputClick", () => {
      this.folderInput?.click();
    });
    __publicField(this, "triggerVideoCameraInputClick", () => {
      this.mobileVideoFileInput?.click();
    });
    __publicField(this, "triggerPhotoCameraInputClick", () => {
      this.mobilePhotoFileInput?.click();
    });
    __publicField(this, "onFileInputChange", (event) => {
      this.props.handleInputChange(event);
      event.currentTarget.value = "";
    });
    __publicField(this, "renderHiddenInput", (isFolder, refCallback) => {
      return u3("input", {
        className: "uppy-Dashboard-input",
        hidden: true,
        "aria-hidden": "true",
        tabIndex: -1,
        // @ts-expect-error default types don't yet know about the `webkitdirectory` property
        webkitdirectory: isFolder,
        type: "file",
        name: "files[]",
        multiple: this.props.maxNumberOfFiles !== 1,
        onChange: this.onFileInputChange,
        accept: this.props.allowedFileTypes?.join(", "),
        ref: refCallback
      });
    });
    __publicField(this, "renderHiddenCameraInput", (type, nativeCameraFacingMode, refCallback) => {
      const typeToAccept = { photo: "image/*", video: "video/*" };
      const accept = typeToAccept[type];
      return u3("input", { className: "uppy-Dashboard-input", hidden: true, "aria-hidden": "true", tabIndex: -1, type: "file", name: `camera-${type}`, onChange: this.onFileInputChange, capture: nativeCameraFacingMode === "" ? "environment" : nativeCameraFacingMode, accept, ref: refCallback });
    });
    __publicField(this, "renderMyDeviceAcquirer", () => {
      return u3("div", { className: "uppy-DashboardTab", role: "presentation", "data-uppy-acquirer-id": "MyDevice", children: u3("button", { type: "button", className: "uppy-u-reset uppy-c-btn uppy-DashboardTab-btn", role: "tab", tabIndex: 0, "data-uppy-super-focusable": true, onClick: this.triggerFileInputClick, children: [u3("div", { className: "uppy-DashboardTab-inner", children: u3("svg", { className: "uppy-DashboardTab-iconMyDevice", "aria-hidden": "true", focusable: "false", width: "32", height: "32", viewBox: "0 0 32 32", children: u3("path", { d: "M8.45 22.087l-1.305-6.674h17.678l-1.572 6.674H8.45zm4.975-12.412l1.083 1.765a.823.823 0 00.715.386h7.951V13.5H8.587V9.675h4.838zM26.043 13.5h-1.195v-2.598c0-.463-.336-.75-.798-.75h-8.356l-1.082-1.766A.823.823 0 0013.897 8H7.728c-.462 0-.815.256-.815.718V13.5h-.956a.97.97 0 00-.746.37.972.972 0 00-.19.81l1.724 8.565c.095.44.484.755.933.755H24c.44 0 .824-.3.929-.727l2.043-8.568a.972.972 0 00-.176-.825.967.967 0 00-.753-.38z", fill: "currentcolor", "fill-rule": "evenodd" }) }) }), u3("div", { className: "uppy-DashboardTab-name", children: this.props.i18n("myDevice") })] }) });
    });
    __publicField(this, "renderPhotoCamera", () => {
      return u3("div", { className: "uppy-DashboardTab", role: "presentation", "data-uppy-acquirer-id": "MobilePhotoCamera", children: u3("button", { type: "button", className: "uppy-u-reset uppy-c-btn uppy-DashboardTab-btn", role: "tab", tabIndex: 0, "data-uppy-super-focusable": true, onClick: this.triggerPhotoCameraInputClick, children: [u3("div", { className: "uppy-DashboardTab-inner", children: u3("svg", { "aria-hidden": "true", focusable: "false", width: "32", height: "32", viewBox: "0 0 32 32", children: u3("path", { d: "M23.5 9.5c1.417 0 2.5 1.083 2.5 2.5v9.167c0 1.416-1.083 2.5-2.5 2.5h-15c-1.417 0-2.5-1.084-2.5-2.5V12c0-1.417 1.083-2.5 2.5-2.5h2.917l1.416-2.167C13 7.167 13.25 7 13.5 7h5c.25 0 .5.167.667.333L20.583 9.5H23.5zM16 11.417a4.706 4.706 0 00-4.75 4.75 4.704 4.704 0 004.75 4.75 4.703 4.703 0 004.75-4.75c0-2.663-2.09-4.75-4.75-4.75zm0 7.825c-1.744 0-3.076-1.332-3.076-3.074 0-1.745 1.333-3.077 3.076-3.077 1.744 0 3.074 1.333 3.074 3.076s-1.33 3.075-3.074 3.075z", fill: "#02B383", "fill-rule": "nonzero" }) }) }), u3("div", { className: "uppy-DashboardTab-name", children: this.props.i18n("takePictureBtn") })] }) });
    });
    __publicField(this, "renderVideoCamera", () => {
      return u3("div", { className: "uppy-DashboardTab", role: "presentation", "data-uppy-acquirer-id": "MobileVideoCamera", children: u3("button", { type: "button", className: "uppy-u-reset uppy-c-btn uppy-DashboardTab-btn", role: "tab", tabIndex: 0, "data-uppy-super-focusable": true, onClick: this.triggerVideoCameraInputClick, children: [u3("div", { className: "uppy-DashboardTab-inner", children: u3("svg", { "aria-hidden": "true", width: "32", height: "32", viewBox: "0 0 32 32", children: u3("path", { fill: "#FF675E", fillRule: "nonzero", d: "m21.254 14.277 2.941-2.588c.797-.313 1.243.818 1.09 1.554-.01 2.094.02 4.189-.017 6.282-.126.915-1.145 1.08-1.58.34l-2.434-2.142c-.192.287-.504 1.305-.738.468-.104-1.293-.028-2.596-.05-3.894.047-.312.381.823.426 1.069.063-.384.206-.744.362-1.09zm-12.939-3.73c3.858.013 7.717-.025 11.574.02.912.129 1.492 1.237 1.351 2.217-.019 2.412.04 4.83-.03 7.239-.17 1.025-1.166 1.59-2.029 1.429-3.705-.012-7.41.025-11.114-.019-.913-.129-1.492-1.237-1.352-2.217.018-2.404-.036-4.813.029-7.214.136-.82.83-1.473 1.571-1.454z " }) }) }), u3("div", { className: "uppy-DashboardTab-name", children: this.props.i18n("recordVideoBtn") })] }) });
    });
    __publicField(this, "renderBrowseButton", (text, onClickFn) => {
      const numberOfAcquirers = this.props.acquirers.length;
      return u3("button", { type: "button", className: "uppy-u-reset uppy-c-btn uppy-Dashboard-browse", onClick: onClickFn, "data-uppy-super-focusable": numberOfAcquirers === 0, children: text });
    });
    __publicField(this, "renderDropPasteBrowseTagline", (numberOfAcquirers) => {
      const browseFiles = this.renderBrowseButton(this.props.i18n("browseFiles"), this.triggerFileInputClick);
      const browseFolders = this.renderBrowseButton(this.props.i18n("browseFolders"), this.triggerFolderInputClick);
      const lowerFMSelectionType = this.props.fileManagerSelectionType;
      const camelFMSelectionType = lowerFMSelectionType.charAt(0).toUpperCase() + lowerFMSelectionType.slice(1);
      return u3("div", { class: "uppy-Dashboard-AddFiles-title", children: this.props.disableLocalFiles ? this.props.i18n("importFiles") : numberOfAcquirers > 0 ? this.props.i18nArray(`dropPasteImport${camelFMSelectionType}`, {
        browseFiles,
        browseFolders,
        browse: browseFiles
      }) : this.props.i18nArray(`dropPaste${camelFMSelectionType}`, {
        browseFiles,
        browseFolders,
        browse: browseFiles
      }) });
    });
    __publicField(this, "renderAcquirer", (acquirer) => {
      return u3("div", { className: "uppy-DashboardTab", role: "presentation", "data-uppy-acquirer-id": acquirer.id, children: u3("button", { type: "button", className: "uppy-u-reset uppy-c-btn uppy-DashboardTab-btn", role: "tab", tabIndex: 0, "data-cy": acquirer.id, "aria-controls": `uppy-DashboardContent-panel--${acquirer.id}`, "aria-selected": this.props.activePickerPanel?.id === acquirer.id, "data-uppy-super-focusable": true, onClick: () => this.props.showPanel(acquirer.id), children: [u3("div", { className: "uppy-DashboardTab-inner", children: acquirer.icon() }), u3("div", { className: "uppy-DashboardTab-name", children: acquirer.name })] }) });
    });
    __publicField(this, "renderAcquirers", (acquirers) => {
      const acquirersWithoutLastTwo = [...acquirers];
      const lastTwoAcquirers = acquirersWithoutLastTwo.splice(acquirers.length - 2, acquirers.length);
      return u3(S, { children: [acquirersWithoutLastTwo.map((acquirer) => this.renderAcquirer(acquirer)), u3("span", { role: "presentation", style: { "white-space": "nowrap" }, children: lastTwoAcquirers.map((acquirer) => this.renderAcquirer(acquirer)) })] });
    });
    __publicField(this, "renderSourcesList", (acquirers, disableLocalFiles) => {
      const { showNativePhotoCameraButton, showNativeVideoCameraButton } = this.props;
      let list = [];
      const myDeviceKey = "myDevice";
      if (!disableLocalFiles)
        list.push({
          key: myDeviceKey,
          elements: this.renderMyDeviceAcquirer()
        });
      if (showNativePhotoCameraButton)
        list.push({
          key: "nativePhotoCameraButton",
          elements: this.renderPhotoCamera()
        });
      if (showNativeVideoCameraButton)
        list.push({
          key: "nativePhotoCameraButton",
          elements: this.renderVideoCamera()
        });
      list.push(...acquirers.map((acquirer) => ({
        key: acquirer.id,
        elements: this.renderAcquirer(acquirer)
      })));
      const hasOnlyMyDevice = list.length === 1 && list[0].key === myDeviceKey;
      if (hasOnlyMyDevice)
        list = [];
      const listWithoutLastTwo = [...list];
      const lastTwo = listWithoutLastTwo.splice(list.length - 2, list.length);
      return u3(S, { children: [this.renderDropPasteBrowseTagline(list.length), u3("div", { className: "uppy-Dashboard-AddFiles-list", role: "tablist", children: [listWithoutLastTwo.map(({ key, elements }) => u3(S, { children: elements }, key)), u3("span", { role: "presentation", style: { "white-space": "nowrap" }, children: lastTwo.map(({ key, elements }) => u3(S, { children: elements }, key)) })] })] });
    });
  }
  [Symbol.for("uppy test: disable unused locale key warning")]() {
    this.props.i18nArray("dropPasteBoth");
    this.props.i18nArray("dropPasteFiles");
    this.props.i18nArray("dropPasteFolders");
    this.props.i18nArray("dropPasteImportBoth");
    this.props.i18nArray("dropPasteImportFiles");
    this.props.i18nArray("dropPasteImportFolders");
  }
  renderPoweredByUppy() {
    const { i18nArray } = this.props;
    const uppyBranding = u3("span", { children: [u3("svg", { "aria-hidden": "true", focusable: "false", className: "uppy-c-icon uppy-Dashboard-poweredByIcon", width: "11", height: "11", viewBox: "0 0 11 11", children: u3("path", { d: "M7.365 10.5l-.01-4.045h2.612L5.5.806l-4.467 5.65h2.604l.01 4.044h3.718z", fillRule: "evenodd" }) }), u3("span", { className: "uppy-Dashboard-poweredByUppy", children: "Uppy" })] });
    const linkText = i18nArray("poweredBy", { uppy: uppyBranding });
    return u3("a", { tabIndex: -1, href: "https://uppy.io", rel: "noreferrer noopener", target: "_blank", className: "uppy-Dashboard-poweredBy", children: linkText });
  }
  render() {
    const { showNativePhotoCameraButton, showNativeVideoCameraButton, nativeCameraFacingMode } = this.props;
    return u3("div", { className: "uppy-Dashboard-AddFiles", children: [this.renderHiddenInput(false, (ref) => {
      this.fileInput = ref;
    }), this.renderHiddenInput(true, (ref) => {
      this.folderInput = ref;
    }), showNativePhotoCameraButton && this.renderHiddenCameraInput("photo", nativeCameraFacingMode, (ref) => {
      this.mobilePhotoFileInput = ref;
    }), showNativeVideoCameraButton && this.renderHiddenCameraInput("video", nativeCameraFacingMode, (ref) => {
      this.mobileVideoFileInput = ref;
    }), this.renderSourcesList(this.props.acquirers, this.props.disableLocalFiles), u3("div", { className: "uppy-Dashboard-AddFiles-info", children: [this.props.note && u3("div", { className: "uppy-Dashboard-note", children: this.props.note }), this.props.proudlyDisplayPoweredByUppy && this.renderPoweredByUppy()] })] });
  }
};
var AddFiles_default = AddFiles;

// node_modules/@uppy/dashboard/lib/components/AddFilesPanel.js
var import_classnames8 = __toESM(require_classnames(), 1);
var AddFilesPanel = (props) => {
  return u3("div", { className: (0, import_classnames8.default)("uppy-Dashboard-AddFilesPanel", props.className), "data-uppy-panelType": "AddFiles", "aria-hidden": !props.showAddFilesPanel, children: [u3("div", { className: "uppy-DashboardContent-bar", children: [u3("div", {
    className: "uppy-DashboardContent-title",
    // biome-ignore lint/a11y/useSemanticElements: ...
    role: "heading",
    "aria-level": 1,
    children: props.i18n("addingMoreFiles")
  }), u3("button", { className: "uppy-DashboardContent-back", type: "button", onClick: () => props.toggleAddFilesPanel(false), children: props.i18n("back") })] }), u3(AddFiles_default, { ...props })] });
};
var AddFilesPanel_default = AddFilesPanel;

// node_modules/@uppy/dashboard/lib/components/EditorPanel.js
var import_classnames9 = __toESM(require_classnames(), 1);
function EditorPanel(props) {
  const file = props.files[props.fileCardFor];
  const handleCancel = () => {
    props.uppy.emit("file-editor:cancel", file);
    props.closeFileEditor();
  };
  return u3("div", { className: (0, import_classnames9.default)("uppy-DashboardContent-panel", props.className), role: "tabpanel", "data-uppy-panelType": "FileEditor", id: "uppy-DashboardContent-panel--editor", children: [u3("div", { className: "uppy-DashboardContent-bar", children: [u3("div", {
    className: "uppy-DashboardContent-title",
    // biome-ignore lint/a11y/useSemanticElements: ...
    role: "heading",
    "aria-level": 1,
    children: props.i18nArray("editing", {
      file: u3("span", { className: "uppy-DashboardContent-titleFile", children: file.meta ? file.meta.name : file.name })
    })
  }), u3("button", { className: "uppy-DashboardContent-back", type: "button", onClick: handleCancel, children: props.i18n("cancel") }), u3("button", { className: "uppy-DashboardContent-save", type: "button", onClick: props.saveFileEditor, children: props.i18n("save") })] }), u3("div", { className: "uppy-DashboardContent-panelBody", children: props.editors.map((target) => {
    return props.uppy.getPlugin(target.id).render(props.state);
  }) })] });
}
var EditorPanel_default = EditorPanel;

// node_modules/@uppy/dashboard/lib/components/FileCard/index.js
var import_classnames10 = __toESM(require_classnames(), 1);

// node_modules/@uppy/dashboard/lib/utils/getFileTypeIcon.js
function iconImage() {
  return u3("svg", { "aria-hidden": "true", focusable: "false", width: "25", height: "25", viewBox: "0 0 25 25", children: u3("g", { fill: "#686DE0", fillRule: "evenodd", children: [u3("path", { d: "M5 7v10h15V7H5zm0-1h15a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1z", fillRule: "nonzero" }), u3("path", { d: "M6.35 17.172l4.994-5.026a.5.5 0 0 1 .707 0l2.16 2.16 3.505-3.505a.5.5 0 0 1 .707 0l2.336 2.31-.707.72-1.983-1.97-3.505 3.505a.5.5 0 0 1-.707 0l-2.16-2.159-3.938 3.939-1.409.026z", fillRule: "nonzero" }), u3("circle", { cx: "7.5", cy: "9.5", r: "1.5" })] }) });
}
function iconAudio() {
  return u3("svg", { "aria-hidden": "true", focusable: "false", className: "uppy-c-icon", width: "25", height: "25", viewBox: "0 0 25 25", children: u3("path", { d: "M9.5 18.64c0 1.14-1.145 2-2.5 2s-2.5-.86-2.5-2c0-1.14 1.145-2 2.5-2 .557 0 1.079.145 1.5.396V7.25a.5.5 0 0 1 .379-.485l9-2.25A.5.5 0 0 1 18.5 5v11.64c0 1.14-1.145 2-2.5 2s-2.5-.86-2.5-2c0-1.14 1.145-2 2.5-2 .557 0 1.079.145 1.5.396V8.67l-8 2v7.97zm8-11v-2l-8 2v2l8-2zM7 19.64c.855 0 1.5-.484 1.5-1s-.645-1-1.5-1-1.5.484-1.5 1 .645 1 1.5 1zm9-2c.855 0 1.5-.484 1.5-1s-.645-1-1.5-1-1.5.484-1.5 1 .645 1 1.5 1z", fill: "#049BCF", fillRule: "nonzero" }) });
}
function iconVideo() {
  return u3("svg", { "aria-hidden": "true", focusable: "false", className: "uppy-c-icon", width: "25", height: "25", viewBox: "0 0 25 25", children: u3("path", { d: "M16 11.834l4.486-2.691A1 1 0 0 1 22 10v6a1 1 0 0 1-1.514.857L16 14.167V17a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v2.834zM15 9H5v8h10V9zm1 4l5 3v-6l-5 3z", fill: "#19AF67", fillRule: "nonzero" }) });
}
function iconPDF() {
  return u3("svg", { "aria-hidden": "true", focusable: "false", className: "uppy-c-icon", width: "25", height: "25", viewBox: "0 0 25 25", children: u3("path", { d: "M9.766 8.295c-.691-1.843-.539-3.401.747-3.726 1.643-.414 2.505.938 2.39 3.299-.039.79-.194 1.662-.537 3.148.324.49.66.967 1.055 1.51.17.231.382.488.629.757 1.866-.128 3.653.114 4.918.655 1.487.635 2.192 1.685 1.614 2.84-.566 1.133-1.839 1.084-3.416.249-1.141-.604-2.457-1.634-3.51-2.707a13.467 13.467 0 0 0-2.238.426c-1.392 4.051-4.534 6.453-5.707 4.572-.986-1.58 1.38-4.206 4.914-5.375.097-.322.185-.656.264-1.001.08-.353.306-1.31.407-1.737-.678-1.059-1.2-2.031-1.53-2.91zm2.098 4.87c-.033.144-.068.287-.104.427l.033-.01-.012.038a14.065 14.065 0 0 1 1.02-.197l-.032-.033.052-.004a7.902 7.902 0 0 1-.208-.271c-.197-.27-.38-.526-.555-.775l-.006.028-.002-.003c-.076.323-.148.632-.186.8zm5.77 2.978c1.143.605 1.832.632 2.054.187.26-.519-.087-1.034-1.113-1.473-.911-.39-2.175-.608-3.55-.608.845.766 1.787 1.459 2.609 1.894zM6.559 18.789c.14.223.693.16 1.425-.413.827-.648 1.61-1.747 2.208-3.206-2.563 1.064-4.102 2.867-3.633 3.62zm5.345-10.97c.088-1.793-.351-2.48-1.146-2.28-.473.119-.564 1.05-.056 2.405.213.566.52 1.188.908 1.859.18-.858.268-1.453.294-1.984z", fill: "#E2514A", fillRule: "nonzero" }) });
}
function iconArchive() {
  return u3("svg", { "aria-hidden": "true", focusable: "false", width: "25", height: "25", viewBox: "0 0 25 25", children: u3("path", { d: "M10.45 2.05h1.05a.5.5 0 0 1 .5.5v.024a.5.5 0 0 1-.5.5h-1.05a.5.5 0 0 1-.5-.5V2.55a.5.5 0 0 1 .5-.5zm2.05 1.024h1.05a.5.5 0 0 1 .5.5V3.6a.5.5 0 0 1-.5.5H12.5a.5.5 0 0 1-.5-.5v-.025a.5.5 0 0 1 .5-.5v-.001zM10.45 0h1.05a.5.5 0 0 1 .5.5v.025a.5.5 0 0 1-.5.5h-1.05a.5.5 0 0 1-.5-.5V.5a.5.5 0 0 1 .5-.5zm2.05 1.025h1.05a.5.5 0 0 1 .5.5v.024a.5.5 0 0 1-.5.5H12.5a.5.5 0 0 1-.5-.5v-.024a.5.5 0 0 1 .5-.5zm-2.05 3.074h1.05a.5.5 0 0 1 .5.5v.025a.5.5 0 0 1-.5.5h-1.05a.5.5 0 0 1-.5-.5v-.025a.5.5 0 0 1 .5-.5zm2.05 1.025h1.05a.5.5 0 0 1 .5.5v.024a.5.5 0 0 1-.5.5H12.5a.5.5 0 0 1-.5-.5v-.024a.5.5 0 0 1 .5-.5zm-2.05 1.024h1.05a.5.5 0 0 1 .5.5v.025a.5.5 0 0 1-.5.5h-1.05a.5.5 0 0 1-.5-.5v-.025a.5.5 0 0 1 .5-.5zm2.05 1.025h1.05a.5.5 0 0 1 .5.5v.025a.5.5 0 0 1-.5.5H12.5a.5.5 0 0 1-.5-.5v-.025a.5.5 0 0 1 .5-.5zm-2.05 1.025h1.05a.5.5 0 0 1 .5.5v.025a.5.5 0 0 1-.5.5h-1.05a.5.5 0 0 1-.5-.5v-.025a.5.5 0 0 1 .5-.5zm2.05 1.025h1.05a.5.5 0 0 1 .5.5v.024a.5.5 0 0 1-.5.5H12.5a.5.5 0 0 1-.5-.5v-.024a.5.5 0 0 1 .5-.5zm-1.656 3.074l-.82 5.946c.52.302 1.174.458 1.976.458.803 0 1.455-.156 1.975-.458l-.82-5.946h-2.311zm0-1.025h2.312c.512 0 .946.378 1.015.885l.82 5.946c.056.412-.142.817-.501 1.026-.686.398-1.515.597-2.49.597-.974 0-1.804-.199-2.49-.597a1.025 1.025 0 0 1-.5-1.026l.819-5.946c.07-.507.503-.885 1.015-.885zm.545 6.6a.5.5 0 0 1-.397-.561l.143-.999a.5.5 0 0 1 .495-.429h.74a.5.5 0 0 1 .495.43l.143.998a.5.5 0 0 1-.397.561c-.404.08-.819.08-1.222 0z", fill: "#00C469", fillRule: "nonzero" }) });
}
function iconFile() {
  return u3("svg", { "aria-hidden": "true", focusable: "false", className: "uppy-c-icon", width: "25", height: "25", viewBox: "0 0 25 25", children: u3("g", { fill: "#A7AFB7", fillRule: "nonzero", children: [u3("path", { d: "M5.5 22a.5.5 0 0 1-.5-.5v-18a.5.5 0 0 1 .5-.5h10.719a.5.5 0 0 1 .367.16l3.281 3.556a.5.5 0 0 1 .133.339V21.5a.5.5 0 0 1-.5.5h-14zm.5-1h13V7.25L16 4H6v17z" }), u3("path", { d: "M15 4v3a1 1 0 0 0 1 1h3V7h-3V4h-1z" })] }) });
}
function iconText() {
  return u3("svg", { "aria-hidden": "true", focusable: "false", className: "uppy-c-icon", width: "25", height: "25", viewBox: "0 0 25 25", children: u3("path", { d: "M4.5 7h13a.5.5 0 1 1 0 1h-13a.5.5 0 0 1 0-1zm0 3h15a.5.5 0 1 1 0 1h-15a.5.5 0 1 1 0-1zm0 3h15a.5.5 0 1 1 0 1h-15a.5.5 0 1 1 0-1zm0 3h10a.5.5 0 1 1 0 1h-10a.5.5 0 1 1 0-1z", fill: "#5A5E69", fillRule: "nonzero" }) });
}
function getIconByMime(fileType) {
  const defaultChoice = {
    color: "#838999",
    icon: iconFile()
  };
  if (!fileType)
    return defaultChoice;
  const fileTypeGeneral = fileType.split("/")[0];
  const fileTypeSpecific = fileType.split("/")[1];
  if (fileTypeGeneral === "text") {
    return {
      color: "#5a5e69",
      icon: iconText()
    };
  }
  if (fileTypeGeneral === "image") {
    return {
      color: "#686de0",
      icon: iconImage()
    };
  }
  if (fileTypeGeneral === "audio") {
    return {
      color: "#068dbb",
      icon: iconAudio()
    };
  }
  if (fileTypeGeneral === "video") {
    return {
      color: "#19af67",
      icon: iconVideo()
    };
  }
  if (fileTypeGeneral === "application" && fileTypeSpecific === "pdf") {
    return {
      color: "#e25149",
      icon: iconPDF()
    };
  }
  const archiveTypes = [
    "zip",
    "x-7z-compressed",
    "x-zip-compressed",
    "x-rar-compressed",
    "x-tar",
    "x-gzip",
    "x-apple-diskimage"
  ];
  if (fileTypeGeneral === "application" && archiveTypes.indexOf(fileTypeSpecific) !== -1) {
    return {
      color: "#00C469",
      icon: iconArchive()
    };
  }
  return defaultChoice;
}

// node_modules/@uppy/dashboard/lib/utils/ignoreEvent.js
function ignoreEvent(ev) {
  const { tagName } = ev.target;
  if (tagName === "INPUT" || tagName === "TEXTAREA") {
    ev.stopPropagation();
    return;
  }
  ev.preventDefault();
  ev.stopPropagation();
}
var ignoreEvent_default = ignoreEvent;

// node_modules/@uppy/dashboard/lib/components/FilePreview.js
function FilePreview(props) {
  const { file } = props;
  if (file.preview) {
    return u3("img", { draggable: false, className: "uppy-Dashboard-Item-previewImg", alt: file.name, src: file.preview });
  }
  const { color, icon } = getIconByMime(file.type);
  return u3("div", { className: "uppy-Dashboard-Item-previewIconWrap", children: [u3("span", { className: "uppy-Dashboard-Item-previewIcon", style: { color }, children: icon }), u3("svg", { "aria-hidden": "true", focusable: "false", className: "uppy-Dashboard-Item-previewIconBg", width: "58", height: "76", viewBox: "0 0 58 76", children: u3("rect", { fill: "#FFF", width: "58", height: "76", rx: "3", fillRule: "evenodd" }) })] });
}

// node_modules/@uppy/dashboard/lib/components/FileCard/RenderMetaFields.js
function RenderMetaFields(props) {
  const { computedMetaFields, requiredMetaFields, updateMeta, form, formState } = props;
  const fieldCSSClasses = {
    text: "uppy-u-reset uppy-c-textInput uppy-Dashboard-FileCard-input"
  };
  return computedMetaFields.map((field) => {
    const id = `uppy-Dashboard-FileCard-input-${field.id}`;
    const required = requiredMetaFields.includes(field.id);
    return u3("fieldset", { className: "uppy-Dashboard-FileCard-fieldset", children: [u3("label", { className: "uppy-Dashboard-FileCard-label", htmlFor: id, children: field.name }), field.render !== void 0 ? field.render({
      value: formState[field.id],
      onChange: (newVal) => updateMeta(newVal, field.id),
      fieldCSSClasses,
      required,
      form: form.id
    }, k) : u3("input", { className: fieldCSSClasses.text, id, form: form.id, type: field.type || "text", required, value: formState[field.id], placeholder: field.placeholder, onInput: (ev) => updateMeta(ev.target.value, field.id), "data-uppy-super-focusable": true })] }, field.id);
  });
}

// node_modules/@uppy/dashboard/lib/components/FileCard/index.js
function FileCard(props) {
  const { files, fileCardFor, toggleFileCard, saveFileCard, metaFields, requiredMetaFields, openFileEditor, i18n, i18nArray, className, canEditFile } = props;
  const getMetaFields = () => {
    return typeof metaFields === "function" ? metaFields(files[fileCardFor]) : metaFields;
  };
  const file = files[fileCardFor];
  const computedMetaFields = getMetaFields() ?? [];
  const showEditButton = canEditFile(file);
  const storedMetaData = {};
  computedMetaFields.forEach((field) => {
    storedMetaData[field.id] = file.meta[field.id] ?? "";
  });
  const [formState, setFormState] = d2(storedMetaData);
  const handleSave = q2((ev) => {
    ev.preventDefault();
    saveFileCard(formState, fileCardFor);
  }, [saveFileCard, formState, fileCardFor]);
  const updateMeta = (newVal, name) => {
    setFormState({
      ...formState,
      [name]: newVal
    });
  };
  const handleCancel = () => {
    toggleFileCard(false);
  };
  const [form] = d2(() => {
    const formEl = document.createElement("form");
    formEl.setAttribute("tabindex", "-1");
    formEl.id = nanoid3();
    return formEl;
  });
  h2(() => {
    document.body.appendChild(form);
    form.addEventListener("submit", handleSave);
    return () => {
      form.removeEventListener("submit", handleSave);
      document.body.removeChild(form);
    };
  }, [form, handleSave]);
  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: ...
    u3("div", { className: (0, import_classnames10.default)("uppy-Dashboard-FileCard", className), "data-uppy-panelType": "FileCard", onDragOver: ignoreEvent_default, onDragLeave: ignoreEvent_default, onDrop: ignoreEvent_default, onPaste: ignoreEvent_default, children: [u3("div", { className: "uppy-DashboardContent-bar", children: [u3("div", {
      className: "uppy-DashboardContent-title",
      // biome-ignore lint/a11y/useSemanticElements: ...
      role: "heading",
      "aria-level": 1,
      children: i18nArray("editing", {
        file: u3("span", { className: "uppy-DashboardContent-titleFile", children: file.meta ? file.meta.name : file.name })
      })
    }), u3("button", { className: "uppy-DashboardContent-back", type: "button", form: form.id, title: i18n("finishEditingFile"), onClick: handleCancel, children: i18n("cancel") })] }), u3("div", { className: "uppy-Dashboard-FileCard-inner", children: [u3("div", { className: "uppy-Dashboard-FileCard-preview", style: { backgroundColor: getIconByMime(file.type).color }, children: [u3(FilePreview, { file }), showEditButton && u3("button", { type: "button", className: "uppy-u-reset uppy-c-btn uppy-Dashboard-FileCard-edit", onClick: (event) => {
      handleSave(event);
      openFileEditor(file);
    }, children: i18n("editImage") })] }), u3("div", { className: "uppy-Dashboard-FileCard-info", children: u3(RenderMetaFields, { computedMetaFields, requiredMetaFields, updateMeta, form, formState }) }), u3("div", { className: "uppy-Dashboard-FileCard-actions", children: [u3("button", {
      className: "uppy-u-reset uppy-c-btn uppy-c-btn-primary uppy-Dashboard-FileCard-actionsBtn",
      // If `form` attribute is supported, we want a submit button to trigger the form validation.
      // Otherwise, fallback to a classic button with a onClick event handler.
      type: "submit",
      form: form.id,
      children: i18n("saveChanges")
    }), u3("button", { className: "uppy-u-reset uppy-c-btn uppy-c-btn-link uppy-Dashboard-FileCard-actionsBtn", type: "button", onClick: handleCancel, form: form.id, children: i18n("cancel") })] })] })] })
  );
}

// node_modules/@uppy/dashboard/lib/components/FileItem/index.js
var import_classnames11 = __toESM(require_classnames(), 1);

// node_modules/shallow-equal/dist/index.modern.mjs
function shallowEqualObjects(objA, objB) {
  if (objA === objB) {
    return true;
  }
  if (!objA || !objB) {
    return false;
  }
  const aKeys = Object.keys(objA);
  const bKeys = Object.keys(objB);
  const len = aKeys.length;
  if (bKeys.length !== len) {
    return false;
  }
  for (let i4 = 0; i4 < len; i4++) {
    const key = aKeys[i4];
    if (objA[key] !== objB[key] || !Object.prototype.hasOwnProperty.call(objB, key)) {
      return false;
    }
  }
  return true;
}

// node_modules/@uppy/dashboard/lib/utils/copyToClipboard.js
function copyToClipboard(textToCopy, fallbackString = "Copy the URL below") {
  return new Promise((resolve) => {
    const textArea = document.createElement("textarea");
    textArea.setAttribute("style", {
      position: "fixed",
      top: 0,
      left: 0,
      width: "2em",
      height: "2em",
      padding: 0,
      border: "none",
      outline: "none",
      boxShadow: "none",
      background: "transparent"
    });
    textArea.value = textToCopy;
    document.body.appendChild(textArea);
    textArea.select();
    const magicCopyFailed = () => {
      document.body.removeChild(textArea);
      window.prompt(fallbackString, textToCopy);
      resolve();
    };
    try {
      const successful = document.execCommand("copy");
      if (!successful) {
        return magicCopyFailed();
      }
      document.body.removeChild(textArea);
      return resolve();
    } catch (_err) {
      document.body.removeChild(textArea);
      return magicCopyFailed();
    }
  });
}

// node_modules/@uppy/dashboard/lib/components/FileItem/Buttons/index.js
function EditButton({ file, uploadInProgressOrComplete, metaFields, canEditFile, i18n, onClick }) {
  if (!uploadInProgressOrComplete && metaFields && metaFields.length > 0 || !uploadInProgressOrComplete && canEditFile(file)) {
    return u3("button", { className: "uppy-u-reset uppy-c-btn uppy-Dashboard-Item-action uppy-Dashboard-Item-action--edit", type: "button", "aria-label": i18n("editFileWithFilename", { file: file.meta.name }), title: i18n("editFileWithFilename", { file: file.meta.name }), onClick: () => onClick(), children: u3("svg", { "aria-hidden": "true", focusable: "false", className: "uppy-c-icon", width: "14", height: "14", viewBox: "0 0 14 14", children: u3("g", { fillRule: "evenodd", children: [u3("path", { d: "M1.5 10.793h2.793A1 1 0 0 0 5 10.5L11.5 4a1 1 0 0 0 0-1.414L9.707.793a1 1 0 0 0-1.414 0l-6.5 6.5A1 1 0 0 0 1.5 8v2.793zm1-1V8L9 1.5l1.793 1.793-6.5 6.5H2.5z", fillRule: "nonzero" }), u3("rect", { x: "1", y: "12.293", width: "11", height: "1", rx: ".5" }), u3("path", { fillRule: "nonzero", d: "M6.793 2.5L9.5 5.207l.707-.707L7.5 1.793z" })] }) }) });
  }
  return null;
}
function RemoveButton({ i18n, onClick, file }) {
  return u3("button", { className: "uppy-u-reset uppy-Dashboard-Item-action uppy-Dashboard-Item-action--remove", type: "button", "aria-label": i18n("removeFile", { file: file.meta.name }), title: i18n("removeFile", { file: file.meta.name }), onClick: () => onClick(), children: u3("svg", { "aria-hidden": "true", focusable: "false", className: "uppy-c-icon", width: "18", height: "18", viewBox: "0 0 18 18", children: [u3("path", { d: "M9 0C4.034 0 0 4.034 0 9s4.034 9 9 9 9-4.034 9-9-4.034-9-9-9z" }), u3("path", { fill: "#FFF", d: "M13 12.222l-.778.778L9 9.778 5.778 13 5 12.222 8.222 9 5 5.778 5.778 5 9 8.222 12.222 5l.778.778L9.778 9z" })] }) });
}
function CopyLinkButton({ file, uppy, i18n }) {
  const copyLinkToClipboard = (event) => {
    copyToClipboard(file.uploadURL, i18n("copyLinkToClipboardFallback")).then(() => {
      uppy.log("Link copied to clipboard.");
      uppy.info(i18n("copyLinkToClipboardSuccess"), "info", 3e3);
    }).catch(uppy.log).then(() => event.target.focus({ preventScroll: true }));
  };
  return u3("button", { className: "uppy-u-reset uppy-Dashboard-Item-action uppy-Dashboard-Item-action--copyLink", type: "button", "aria-label": i18n("copyLink"), title: i18n("copyLink"), onClick: (event) => copyLinkToClipboard(event), children: u3("svg", { "aria-hidden": "true", focusable: "false", className: "uppy-c-icon", width: "14", height: "14", viewBox: "0 0 14 12", children: u3("path", { d: "M7.94 7.703a2.613 2.613 0 0 1-.626 2.681l-.852.851a2.597 2.597 0 0 1-1.849.766A2.616 2.616 0 0 1 2.764 7.54l.852-.852a2.596 2.596 0 0 1 2.69-.625L5.267 7.099a1.44 1.44 0 0 0-.833.407l-.852.851a1.458 1.458 0 0 0 1.03 2.486c.39 0 .755-.152 1.03-.426l.852-.852c.231-.231.363-.522.406-.824l1.04-1.038zm4.295-5.937A2.596 2.596 0 0 0 10.387 1c-.698 0-1.355.272-1.849.766l-.852.851a2.614 2.614 0 0 0-.624 2.688l1.036-1.036c.041-.304.173-.6.407-.833l.852-.852c.275-.275.64-.426 1.03-.426a1.458 1.458 0 0 1 1.03 2.486l-.852.851a1.442 1.442 0 0 1-.824.406l-1.04 1.04a2.596 2.596 0 0 0 2.683-.628l.851-.85a2.616 2.616 0 0 0 0-3.697zm-6.88 6.883a.577.577 0 0 0 .82 0l3.474-3.474a.579.579 0 1 0-.819-.82L5.355 7.83a.579.579 0 0 0 0 .819z" }) }) });
}
function Buttons(props) {
  const { uppy, file, uploadInProgressOrComplete, canEditFile, metaFields, showLinkToFileUploadResult, showRemoveButton, i18n, toggleFileCard, openFileEditor } = props;
  const editAction = () => {
    if (metaFields && metaFields.length > 0) {
      toggleFileCard(true, file.id);
    } else {
      openFileEditor(file);
    }
  };
  return u3("div", { className: "uppy-Dashboard-Item-actionWrapper", children: [u3(EditButton, { i18n, file, uploadInProgressOrComplete, canEditFile, metaFields, onClick: editAction }), showLinkToFileUploadResult && file.uploadURL ? u3(CopyLinkButton, { file, uppy, i18n }) : null, showRemoveButton ? u3(RemoveButton, { i18n, file, onClick: () => uppy.removeFile(file.id) }) : null] });
}

// node_modules/@uppy/dashboard/lib/components/FileItem/FileInfo/index.js
var import_prettier_bytes3 = __toESM(require_prettierBytes(), 1);

// node_modules/@uppy/utils/lib/truncateString.js
var separator = "...";
function truncateString(string, maxLength) {
  if (maxLength === 0)
    return "";
  if (string.length <= maxLength)
    return string;
  if (maxLength <= separator.length + 1)
    return `${string.slice(0, maxLength - 1)}\u2026`;
  const charsToShow = maxLength - separator.length;
  const frontChars = Math.ceil(charsToShow / 2);
  const backChars = Math.floor(charsToShow / 2);
  return string.slice(0, frontChars) + separator + string.slice(-backChars);
}

// node_modules/@uppy/dashboard/lib/components/FileItem/MetaErrorMessage.js
var metaFieldIdToName = (metaFieldId, metaFields) => {
  const fields = typeof metaFields === "function" ? metaFields() : metaFields;
  const field = fields.filter((f5) => f5.id === metaFieldId);
  return field[0].name;
};
function MetaErrorMessage(props) {
  const { file, toggleFileCard, i18n, metaFields } = props;
  const { missingRequiredMetaFields } = file;
  if (!missingRequiredMetaFields?.length) {
    return null;
  }
  const metaFieldsString = missingRequiredMetaFields.map((missingMetaField) => metaFieldIdToName(missingMetaField, metaFields)).join(", ");
  return u3("div", { className: "uppy-Dashboard-Item-errorMessage", children: [i18n("missingRequiredMetaFields", {
    smart_count: missingRequiredMetaFields.length,
    fields: metaFieldsString
  }), " ", u3("button", { type: "button", class: "uppy-u-reset uppy-Dashboard-Item-errorMessageBtn", onClick: () => toggleFileCard(true, file.id), children: i18n("editFile") })] });
}

// node_modules/@uppy/dashboard/lib/components/FileItem/FileInfo/index.js
var renderFileName = (props) => {
  const { author, name } = props.file.meta;
  function getMaxNameLength() {
    if (props.isSingleFile && props.containerHeight >= 350) {
      return 90;
    }
    if (props.containerWidth <= 352) {
      return 35;
    }
    if (props.containerWidth <= 576) {
      return 60;
    }
    return author ? 20 : 30;
  }
  return u3("div", { className: "uppy-Dashboard-Item-name", title: name, children: truncateString(name, getMaxNameLength()) });
};
var renderAuthor = (props) => {
  const { author } = props.file.meta;
  const providerName = props.file.remote?.providerName;
  const dot = `\xB7`;
  if (!author) {
    return null;
  }
  return u3("div", { className: "uppy-Dashboard-Item-author", children: [u3("a", { href: `${author.url}?utm_source=Companion&utm_medium=referral`, target: "_blank", rel: "noopener noreferrer", children: truncateString(author.name, 13) }), providerName ? u3(S, { children: [` ${dot} `, providerName, ` ${dot} `] }) : null] });
};
var renderFileSize = (props) => props.file.size && u3("div", { className: "uppy-Dashboard-Item-statusSize", children: (0, import_prettier_bytes3.default)(props.file.size) });
var ReSelectButton = (props) => props.file.isGhost && u3("span", { children: [" \u2022 ", u3("button", { className: "uppy-u-reset uppy-c-btn uppy-Dashboard-Item-reSelect", type: "button", onClick: () => props.toggleAddFilesPanel(true), children: props.i18n("reSelect") })] });
var ErrorButton = ({ file, onClick }) => {
  if (file.error) {
    return u3("button", { className: "uppy-u-reset uppy-c-btn uppy-Dashboard-Item-errorDetails", "aria-label": file.error, "data-microtip-position": "bottom", "data-microtip-size": "medium", onClick, type: "button", children: "?" });
  }
  return null;
};
function FileInfo(props) {
  const { file, i18n, toggleFileCard, metaFields, toggleAddFilesPanel, isSingleFile, containerHeight, containerWidth } = props;
  return u3("div", { className: "uppy-Dashboard-Item-fileInfo", "data-uppy-file-source": file.source, children: [u3("div", { className: "uppy-Dashboard-Item-fileName", children: [renderFileName({
    file,
    isSingleFile,
    containerHeight,
    containerWidth
  }), u3(ErrorButton, { file, onClick: () => alert(file.error) })] }), u3("div", { className: "uppy-Dashboard-Item-status", children: [renderAuthor({ file }), renderFileSize({ file }), ReSelectButton({ file, toggleAddFilesPanel, i18n })] }), u3(MetaErrorMessage, { file, i18n, toggleFileCard, metaFields })] });
}

// node_modules/@uppy/dashboard/lib/components/FileItem/FilePreviewAndLink/index.js
function FilePreviewAndLink(props) {
  const { file, i18n, toggleFileCard, metaFields, showLinkToFileUploadResult } = props;
  const white = "rgba(255, 255, 255, 0.5)";
  const previewBackgroundColor = file.preview ? white : getIconByMime(file.type).color;
  return u3("div", { className: "uppy-Dashboard-Item-previewInnerWrap", style: { backgroundColor: previewBackgroundColor }, children: [showLinkToFileUploadResult && file.uploadURL && u3("a", { className: "uppy-Dashboard-Item-previewLink", href: file.uploadURL, rel: "noreferrer noopener", target: "_blank", "aria-label": file.meta.name, children: u3("span", { hidden: true, children: file.meta.name }) }), u3(FilePreview, { file }), u3(MetaErrorMessage, { file, i18n, toggleFileCard, metaFields })] });
}

// node_modules/@uppy/dashboard/lib/components/FileItem/FileProgress/index.js
function onPauseResumeCancelRetry(props) {
  if (props.isUploaded)
    return;
  if (props.error && !props.hideRetryButton) {
    props.uppy.retryUpload(props.file.id);
    return;
  }
  if (props.resumableUploads && !props.hidePauseResumeButton) {
    props.uppy.pauseResume(props.file.id);
  } else if (props.individualCancellation && !props.hideCancelButton) {
    props.uppy.removeFile(props.file.id);
  }
}
function progressIndicatorTitle(props) {
  if (props.isUploaded) {
    return props.i18n("uploadComplete");
  }
  if (props.error) {
    return props.i18n("retryUpload");
  }
  if (props.resumableUploads) {
    if (props.file.isPaused) {
      return props.i18n("resumeUpload");
    }
    return props.i18n("pauseUpload");
  }
  if (props.individualCancellation) {
    return props.i18n("cancelUpload");
  }
  return "";
}
function ProgressIndicatorButton(props) {
  return u3("div", { className: "uppy-Dashboard-Item-progress", children: u3("button", { className: "uppy-u-reset uppy-c-btn uppy-Dashboard-Item-progressIndicator", type: "button", "aria-label": progressIndicatorTitle(props), title: progressIndicatorTitle(props), onClick: () => onPauseResumeCancelRetry(props), children: props.children }) });
}
function ProgressCircleContainer({ children }) {
  return u3("svg", { "aria-hidden": "true", focusable: "false", width: "70", height: "70", viewBox: "0 0 36 36", className: "uppy-c-icon uppy-Dashboard-Item-progressIcon--circle", children });
}
function ProgressCircle({ progress }) {
  const circleLength = 2 * Math.PI * 15;
  return u3("g", { children: [u3("circle", { className: "uppy-Dashboard-Item-progressIcon--bg", r: "15", cx: "18", cy: "18", "stroke-width": "2", fill: "none" }), u3("circle", { className: "uppy-Dashboard-Item-progressIcon--progress", r: "15", cx: "18", cy: "18", transform: "rotate(-90, 18, 18)", fill: "none", "stroke-width": "2", "stroke-dasharray": circleLength, "stroke-dashoffset": circleLength - circleLength / 100 * progress })] });
}
function FileProgress(props) {
  if (!props.file.progress.uploadStarted) {
    return null;
  }
  if (props.file.progress.percentage === void 0) {
    return null;
  }
  if (props.isUploaded) {
    return u3("div", { className: "uppy-Dashboard-Item-progress", children: u3("div", { className: "uppy-Dashboard-Item-progressIndicator", children: u3(ProgressCircleContainer, { children: [u3("circle", { r: "15", cx: "18", cy: "18", fill: "#1bb240" }), u3("polygon", { className: "uppy-Dashboard-Item-progressIcon--check", transform: "translate(2, 3)", points: "14 22.5 7 15.2457065 8.99985857 13.1732815 14 18.3547104 22.9729883 9 25 11.1005634" })] }) }) });
  }
  if (props.recoveredState) {
    return null;
  }
  if (props.error && !props.hideRetryButton) {
    return u3(ProgressIndicatorButton, { ...props, children: u3("svg", { "aria-hidden": "true", focusable: "false", className: "uppy-c-icon uppy-Dashboard-Item-progressIcon--retry", width: "28", height: "31", viewBox: "0 0 16 19", children: [u3("path", { d: "M16 11a8 8 0 1 1-8-8v2a6 6 0 1 0 6 6h2z" }), u3("path", { d: "M7.9 3H10v2H7.9z" }), u3("path", { d: "M8.536.5l3.535 3.536-1.414 1.414L7.12 1.914z" }), u3("path", { d: "M10.657 2.621l1.414 1.415L8.536 7.57 7.12 6.157z" })] }) });
  }
  if (props.resumableUploads && !props.hidePauseResumeButton) {
    return u3(ProgressIndicatorButton, { ...props, children: u3(ProgressCircleContainer, { children: [u3(ProgressCircle, { progress: props.file.progress.percentage }), props.file.isPaused ? u3("polygon", { className: "uppy-Dashboard-Item-progressIcon--play", transform: "translate(3, 3)", points: "12 20 12 10 20 15" }) : u3("g", { className: "uppy-Dashboard-Item-progressIcon--pause", transform: "translate(14.5, 13)", children: [u3("rect", { x: "0", y: "0", width: "2", height: "10", rx: "0" }), u3("rect", { x: "5", y: "0", width: "2", height: "10", rx: "0" })] })] }) });
  }
  if (!props.resumableUploads && props.individualCancellation && !props.hideCancelButton) {
    return u3(ProgressIndicatorButton, { ...props, children: u3(ProgressCircleContainer, { children: [u3(ProgressCircle, { progress: props.file.progress.percentage }), u3("polygon", { className: "cancel", transform: "translate(2, 2)", points: "19.8856516 11.0625 16 14.9481516 12.1019737 11.0625 11.0625 12.1143484 14.9481516 16 11.0625 19.8980263 12.1019737 20.9375 16 17.0518484 19.8856516 20.9375 20.9375 19.8980263 17.0518484 16 20.9375 12" })] }) });
  }
  return u3("div", { className: "uppy-Dashboard-Item-progress", children: u3("div", { className: "uppy-Dashboard-Item-progressIndicator", children: u3(ProgressCircleContainer, { children: u3(ProgressCircle, { progress: props.file.progress.percentage }) }) }) });
}

// node_modules/@uppy/dashboard/lib/components/FileItem/index.js
var FileItem = class extends C {
  componentDidMount() {
    const { file } = this.props;
    if (!file.preview) {
      this.props.handleRequestThumbnail(file);
    }
  }
  shouldComponentUpdate(nextProps) {
    return !shallowEqualObjects(this.props, nextProps);
  }
  // VirtualList mounts FileItems again and they emit `thumbnail:request`
  // Otherwise thumbnails are broken or missing after Golden Retriever restores files
  componentDidUpdate() {
    const { file } = this.props;
    if (!file.preview) {
      this.props.handleRequestThumbnail(file);
    }
  }
  componentWillUnmount() {
    const { file } = this.props;
    if (!file.preview) {
      this.props.handleCancelThumbnail(file);
    }
  }
  render() {
    const { file } = this.props;
    const isProcessing = file.progress.preprocess || file.progress.postprocess;
    const isUploaded = !!file.progress.uploadComplete && !isProcessing && !file.error;
    const uploadInProgressOrComplete = !!file.progress.uploadStarted || !!isProcessing;
    const uploadInProgress = file.progress.uploadStarted && !file.progress.uploadComplete || isProcessing;
    const error = file.error || false;
    const { isGhost } = file;
    let showRemoveButton = this.props.individualCancellation ? !isUploaded : !uploadInProgress && !isUploaded;
    if (isUploaded && this.props.showRemoveButtonAfterComplete) {
      showRemoveButton = true;
    }
    const dashboardItemClass = (0, import_classnames11.default)({
      "uppy-Dashboard-Item": true,
      "is-inprogress": uploadInProgress && !this.props.recoveredState,
      "is-processing": isProcessing,
      "is-complete": isUploaded,
      "is-error": !!error,
      "is-resumable": this.props.resumableUploads,
      "is-noIndividualCancellation": !this.props.individualCancellation,
      "is-ghost": isGhost
    });
    return u3("div", { className: dashboardItemClass, id: `uppy_${file.id}`, role: this.props.role, children: [u3("div", { className: "uppy-Dashboard-Item-preview", children: [u3(FilePreviewAndLink, { file, showLinkToFileUploadResult: this.props.showLinkToFileUploadResult, i18n: this.props.i18n, toggleFileCard: this.props.toggleFileCard, metaFields: this.props.metaFields }), u3(FileProgress, { uppy: this.props.uppy, file, error, isUploaded, hideRetryButton: this.props.hideRetryButton, hideCancelButton: this.props.hideCancelButton, hidePauseResumeButton: this.props.hidePauseResumeButton, recoveredState: this.props.recoveredState, resumableUploads: this.props.resumableUploads, individualCancellation: this.props.individualCancellation, i18n: this.props.i18n })] }), u3("div", { className: "uppy-Dashboard-Item-fileInfoAndButtons", children: [u3(FileInfo, { file, containerWidth: this.props.containerWidth, containerHeight: this.props.containerHeight, i18n: this.props.i18n, toggleAddFilesPanel: this.props.toggleAddFilesPanel, toggleFileCard: this.props.toggleFileCard, metaFields: this.props.metaFields, isSingleFile: this.props.isSingleFile }), u3(Buttons, { file, metaFields: this.props.metaFields, showLinkToFileUploadResult: this.props.showLinkToFileUploadResult, showRemoveButton, canEditFile: this.props.canEditFile, uploadInProgressOrComplete, toggleFileCard: this.props.toggleFileCard, openFileEditor: this.props.openFileEditor, uppy: this.props.uppy, i18n: this.props.i18n })] })] });
  }
};

// node_modules/@uppy/dashboard/lib/components/FileList.js
function chunks(list, size) {
  const chunked = [];
  let currentChunk = [];
  list.forEach((item) => {
    if (currentChunk.length < size) {
      currentChunk.push(item);
    } else {
      chunked.push(currentChunk);
      currentChunk = [item];
    }
  });
  if (currentChunk.length)
    chunked.push(currentChunk);
  return chunked;
}
function FileList({ id, i18n, uppy, files, resumableUploads, hideRetryButton, hidePauseResumeButton, hideCancelButton, showLinkToFileUploadResult, showRemoveButtonAfterComplete, metaFields, isSingleFile, toggleFileCard, handleRequestThumbnail, handleCancelThumbnail, recoveredState, individualCancellation, itemsPerRow, openFileEditor, canEditFile, toggleAddFilesPanel, containerWidth, containerHeight }) {
  const rowHeight = itemsPerRow === 1 ? (
    // Mobile
    71
  ) : (
    // 190px height + 2 * 5px margin
    200
  );
  const rows = T2(() => {
    const sortByGhostComesFirst = (file1, file2) => Number(files[file2].isGhost) - Number(files[file1].isGhost);
    const fileIds = Object.keys(files);
    if (recoveredState)
      fileIds.sort(sortByGhostComesFirst);
    return chunks(fileIds, itemsPerRow);
  }, [files, itemsPerRow, recoveredState]);
  const renderRow = (row) => u3("div", {
    class: "uppy-Dashboard-filesInner",
    // The `role="presentation` attribute ensures that the list items are properly
    // associated with the `VirtualList` element.
    role: "presentation",
    children: row.map((fileID) => u3(FileItem, {
      uppy,
      // FIXME This is confusing, it's actually the Dashboard's plugin ID
      id,
      // TODO move this to context
      i18n,
      // features
      resumableUploads,
      individualCancellation,
      // visual options
      hideRetryButton,
      hidePauseResumeButton,
      hideCancelButton,
      showLinkToFileUploadResult,
      showRemoveButtonAfterComplete,
      metaFields,
      recoveredState,
      isSingleFile,
      containerWidth,
      containerHeight,
      // callbacks
      toggleFileCard,
      handleRequestThumbnail,
      handleCancelThumbnail,
      role: "listitem",
      openFileEditor,
      canEditFile,
      toggleAddFilesPanel,
      file: files[fileID]
    }, fileID))
  }, row[0]);
  if (isSingleFile) {
    return u3("div", { class: "uppy-Dashboard-files", children: renderRow(rows[0]) });
  }
  return u3(VirtualList_default, { class: "uppy-Dashboard-files", role: "list", data: rows, renderRow, rowHeight });
}

// node_modules/@uppy/dashboard/lib/components/PickerPanelContent.js
var import_classnames12 = __toESM(require_classnames(), 1);
function PickerPanelContent({ activePickerPanel, className, hideAllPanels, i18n, state, uppy }) {
  const ref = A2(null);
  return u3("div", { className: (0, import_classnames12.default)("uppy-DashboardContent-panel", className), role: "tabpanel", "data-uppy-panelType": "PickerPanel", id: `uppy-DashboardContent-panel--${activePickerPanel.id}`, onDragOver: ignoreEvent_default, onDragLeave: ignoreEvent_default, onDrop: ignoreEvent_default, onPaste: ignoreEvent_default, children: [u3("div", { className: "uppy-DashboardContent-bar", children: [u3("div", {
    className: "uppy-DashboardContent-title",
    // biome-ignore lint/a11y/useSemanticElements: ...
    role: "heading",
    "aria-level": 1,
    children: i18n("importFrom", { name: activePickerPanel.name })
  }), u3("button", { className: "uppy-DashboardContent-back", type: "button", onClick: hideAllPanels, children: i18n("cancel") })] }), u3("div", { ref, className: "uppy-DashboardContent-panelBody", children: uppy.getPlugin(activePickerPanel.id).render(state, ref.current) })] });
}
var PickerPanelContent_default = PickerPanelContent;

// node_modules/@uppy/dashboard/lib/components/PickerPanelTopBar.js
var uploadStates = {
  STATE_ERROR: "error",
  STATE_WAITING: "waiting",
  STATE_PREPROCESSING: "preprocessing",
  STATE_UPLOADING: "uploading",
  STATE_POSTPROCESSING: "postprocessing",
  STATE_COMPLETE: "complete",
  STATE_PAUSED: "paused"
};
function getUploadingState2(isAllErrored, isAllComplete, isAllPaused, files = {}) {
  if (isAllErrored) {
    return uploadStates.STATE_ERROR;
  }
  if (isAllComplete) {
    return uploadStates.STATE_COMPLETE;
  }
  if (isAllPaused) {
    return uploadStates.STATE_PAUSED;
  }
  let state = uploadStates.STATE_WAITING;
  const fileIDs = Object.keys(files);
  for (let i4 = 0; i4 < fileIDs.length; i4++) {
    const { progress } = files[fileIDs[i4]];
    if (progress.uploadStarted && !progress.uploadComplete) {
      return uploadStates.STATE_UPLOADING;
    }
    if (progress.preprocess && state !== uploadStates.STATE_UPLOADING) {
      state = uploadStates.STATE_PREPROCESSING;
    }
    if (progress.postprocess && state !== uploadStates.STATE_UPLOADING && state !== uploadStates.STATE_PREPROCESSING) {
      state = uploadStates.STATE_POSTPROCESSING;
    }
  }
  return state;
}
function UploadStatus({ files, i18n, isAllComplete, isAllErrored, isAllPaused, inProgressNotPausedFiles, newFiles, processingFiles }) {
  const uploadingState = getUploadingState2(isAllErrored, isAllComplete, isAllPaused, files);
  switch (uploadingState) {
    case "uploading":
      return i18n("uploadingXFiles", {
        smart_count: inProgressNotPausedFiles.length
      });
    case "preprocessing":
    case "postprocessing":
      return i18n("processingXFiles", { smart_count: processingFiles.length });
    case "paused":
      return i18n("uploadPaused");
    case "waiting":
      return i18n("xFilesSelected", { smart_count: newFiles.length });
    case "complete":
      return i18n("uploadComplete");
    case "error":
      return i18n("error");
    default:
  }
}
function PanelTopBar(props) {
  const { i18n, isAllComplete, hideCancelButton, maxNumberOfFiles, toggleAddFilesPanel, uppy } = props;
  let { allowNewUpload } = props;
  if (allowNewUpload && maxNumberOfFiles) {
    allowNewUpload = props.totalFileCount < props.maxNumberOfFiles;
  }
  return u3("div", { className: "uppy-DashboardContent-bar", children: [!isAllComplete && !hideCancelButton ? u3("button", { className: "uppy-DashboardContent-back", type: "button", onClick: () => uppy.cancelAll(), children: i18n("cancel") }) : u3("div", {}), u3("div", { className: "uppy-DashboardContent-title", children: u3(UploadStatus, { ...props }) }), allowNewUpload ? u3("button", { className: "uppy-DashboardContent-addMore", type: "button", "aria-label": i18n("addMoreFiles"), title: i18n("addMoreFiles"), onClick: () => toggleAddFilesPanel(true), children: [u3("svg", { "aria-hidden": "true", focusable: "false", className: "uppy-c-icon", width: "15", height: "15", viewBox: "0 0 15 15", children: u3("path", { d: "M8 6.5h6a.5.5 0 0 1 .5.5v.5a.5.5 0 0 1-.5.5H8v6a.5.5 0 0 1-.5.5H7a.5.5 0 0 1-.5-.5V8h-6a.5.5 0 0 1-.5-.5V7a.5.5 0 0 1 .5-.5h6v-6A.5.5 0 0 1 7 0h.5a.5.5 0 0 1 .5.5v6z" }) }), u3("span", { className: "uppy-DashboardContent-addMoreCaption", children: i18n("addMore") })] }) : u3("div", {})] });
}
var PickerPanelTopBar_default = PanelTopBar;

// node_modules/@uppy/dashboard/lib/components/Slide.js
var import_classnames13 = __toESM(require_classnames(), 1);
var transitionName = "uppy-transition-slideDownUp";
var duration = 250;
function Slide({ children }) {
  const [cachedChildren, setCachedChildren] = d2(null);
  const [className, setClassName] = d2("");
  const enterTimeoutRef = A2();
  const leaveTimeoutRef = A2();
  const animationFrameRef = A2();
  const handleEnterTransition = () => {
    setClassName(`${transitionName}-enter`);
    cancelAnimationFrame(animationFrameRef.current);
    clearTimeout(leaveTimeoutRef.current);
    leaveTimeoutRef.current = void 0;
    animationFrameRef.current = requestAnimationFrame(() => {
      setClassName(`${transitionName}-enter ${transitionName}-enter-active`);
      enterTimeoutRef.current = setTimeout(() => {
        setClassName("");
      }, duration);
    });
  };
  const handleLeaveTransition = () => {
    setClassName(`${transitionName}-leave`);
    cancelAnimationFrame(animationFrameRef.current);
    clearTimeout(enterTimeoutRef.current);
    enterTimeoutRef.current = void 0;
    animationFrameRef.current = requestAnimationFrame(() => {
      setClassName(`${transitionName}-leave ${transitionName}-leave-active`);
      leaveTimeoutRef.current = setTimeout(() => {
        setCachedChildren(null);
        setClassName("");
      }, duration);
    });
  };
  h2(() => {
    const child = F(children)[0];
    if (cachedChildren === child)
      return;
    if (child && !cachedChildren) {
      handleEnterTransition();
    } else if (cachedChildren && !child && !leaveTimeoutRef.current) {
      handleLeaveTransition();
    }
    setCachedChildren(child);
  }, [children, cachedChildren]);
  h2(() => {
    return () => {
      clearTimeout(enterTimeoutRef.current);
      clearTimeout(leaveTimeoutRef.current);
      cancelAnimationFrame(animationFrameRef.current);
    };
  }, []);
  if (!cachedChildren)
    return null;
  return W(cachedChildren, {
    className: (0, import_classnames13.default)(className, cachedChildren.props.className)
  });
}
var Slide_default = Slide;

// node_modules/@uppy/dashboard/lib/components/Dashboard.js
var WIDTH_XL = 900;
var WIDTH_LG = 700;
var WIDTH_MD = 576;
var HEIGHT_MD = 330;
function Dashboard(props) {
  const isNoFiles = props.totalFileCount === 0;
  const isSingleFile = props.totalFileCount === 1;
  const isSizeMD = props.containerWidth > WIDTH_MD;
  const isSizeHeightMD = props.containerHeight > HEIGHT_MD;
  const dashboardClassName = (0, import_classnames14.default)({
    "uppy-Dashboard": true,
    "uppy-Dashboard--isDisabled": props.disabled,
    "uppy-Dashboard--animateOpenClose": props.animateOpenClose,
    "uppy-Dashboard--isClosing": props.isClosing,
    "uppy-Dashboard--isDraggingOver": props.isDraggingOver,
    "uppy-Dashboard--modal": !props.inline,
    "uppy-size--md": props.containerWidth > WIDTH_MD,
    "uppy-size--lg": props.containerWidth > WIDTH_LG,
    "uppy-size--xl": props.containerWidth > WIDTH_XL,
    "uppy-size--height-md": props.containerHeight > HEIGHT_MD,
    // We might want to enable this in the future
    // 'uppy-size--height-lg': props.containerHeight > HEIGHT_LG,
    // 'uppy-size--height-xl': props.containerHeight > HEIGHT_XL,
    "uppy-Dashboard--isAddFilesPanelVisible": props.showAddFilesPanel,
    "uppy-Dashboard--isInnerWrapVisible": props.areInsidesReadyToBeVisible,
    // Only enable “centered single file” mode when Dashboard is tall enough
    "uppy-Dashboard--singleFile": props.singleFileFullScreen && isSingleFile && isSizeHeightMD
  });
  let itemsPerRow = 1;
  if (props.containerWidth > WIDTH_XL) {
    itemsPerRow = 5;
  } else if (props.containerWidth > WIDTH_LG) {
    itemsPerRow = 4;
  } else if (props.containerWidth > WIDTH_MD) {
    itemsPerRow = 3;
  }
  const showFileList = props.showSelectedFiles && !isNoFiles;
  const numberOfFilesForRecovery = props.recoveredState ? Object.keys(props.recoveredState.files).length : null;
  const numberOfGhosts = props.files ? Object.keys(props.files).filter((fileID) => props.files[fileID].isGhost).length : 0;
  const renderRestoredText = () => {
    if (numberOfGhosts > 0) {
      return props.i18n("recoveredXFiles", {
        smart_count: numberOfGhosts
      });
    }
    return props.i18n("recoveredAllFiles");
  };
  const dashboard = (
    // biome-ignore lint/a11y/useAriaPropsSupportedByRole: ...
    u3("div", { className: dashboardClassName, "data-uppy-theme": props.theme, "data-uppy-num-acquirers": props.acquirers.length, "data-uppy-drag-drop-supported": !props.disableLocalFiles && isDragDropSupported(), "aria-hidden": props.inline ? "false" : props.isHidden, "aria-disabled": props.disabled, "aria-label": !props.inline ? props.i18n("dashboardWindowTitle") : props.i18n("dashboardTitle"), onPaste: props.handlePaste, onDragOver: props.handleDragOver, onDragLeave: props.handleDragLeave, onDrop: props.handleDrop, children: [u3("div", { "aria-hidden": "true", className: "uppy-Dashboard-overlay", tabIndex: -1, onClick: props.handleClickOutside }), u3("div", { className: "uppy-Dashboard-inner", role: props.inline ? void 0 : "dialog", style: {
      width: props.inline && props.width ? props.width : "",
      height: props.inline && props.height ? props.height : ""
    }, children: [!props.inline ? u3("button", { className: "uppy-u-reset uppy-Dashboard-close", type: "button", "aria-label": props.i18n("closeModal"), title: props.i18n("closeModal"), onClick: props.closeModal, children: u3("span", { "aria-hidden": "true", children: "\xD7" }) }) : null, u3("div", { className: "uppy-Dashboard-innerWrap", children: [u3("div", { className: "uppy-Dashboard-dropFilesHereHint", children: props.i18n("dropHint") }), showFileList && u3(PickerPanelTopBar_default, { ...props }), numberOfFilesForRecovery && u3("div", { className: "uppy-Dashboard-serviceMsg", children: [u3("svg", { className: "uppy-Dashboard-serviceMsg-icon", "aria-hidden": "true", focusable: "false", width: "21", height: "16", viewBox: "0 0 24 19", children: u3("g", { transform: "translate(0 -1)", fill: "none", fillRule: "evenodd", children: [u3("path", { d: "M12.857 1.43l10.234 17.056A1 1 0 0122.234 20H1.766a1 1 0 01-.857-1.514L11.143 1.429a1 1 0 011.714 0z", fill: "#FFD300" }), u3("path", { fill: "#000", d: "M11 6h2l-.3 8h-1.4z" }), u3("circle", { fill: "#000", cx: "12", cy: "17", r: "1" })] }) }), u3("strong", { className: "uppy-Dashboard-serviceMsg-title", children: props.i18n("sessionRestored") }), u3("div", { className: "uppy-Dashboard-serviceMsg-text", children: renderRestoredText() })] }), showFileList ? u3(FileList, { id: props.id, i18n: props.i18n, uppy: props.uppy, files: props.files, resumableUploads: props.resumableUploads, hideRetryButton: props.hideRetryButton, hidePauseResumeButton: props.hidePauseResumeButton, hideCancelButton: props.hideCancelButton, showLinkToFileUploadResult: props.showLinkToFileUploadResult, showRemoveButtonAfterComplete: props.showRemoveButtonAfterComplete, metaFields: props.metaFields, toggleFileCard: props.toggleFileCard, handleRequestThumbnail: props.handleRequestThumbnail, handleCancelThumbnail: props.handleCancelThumbnail, recoveredState: props.recoveredState, individualCancellation: props.individualCancellation, openFileEditor: props.openFileEditor, canEditFile: props.canEditFile, toggleAddFilesPanel: props.toggleAddFilesPanel, isSingleFile, itemsPerRow, containerWidth: props.containerWidth, containerHeight: props.containerHeight }) : u3(AddFiles_default, { i18n: props.i18n, i18nArray: props.i18nArray, acquirers: props.acquirers, handleInputChange: props.handleInputChange, maxNumberOfFiles: props.maxNumberOfFiles, allowedFileTypes: props.allowedFileTypes, showNativePhotoCameraButton: props.showNativePhotoCameraButton, showNativeVideoCameraButton: props.showNativeVideoCameraButton, nativeCameraFacingMode: props.nativeCameraFacingMode, showPanel: props.showPanel, activePickerPanel: props.activePickerPanel, disableLocalFiles: props.disableLocalFiles, fileManagerSelectionType: props.fileManagerSelectionType, note: props.note, proudlyDisplayPoweredByUppy: props.proudlyDisplayPoweredByUppy }), u3(Slide_default, { children: props.showAddFilesPanel ? u3(AddFilesPanel_default, { ...props, isSizeMD }, "AddFiles") : null }), u3(Slide_default, { children: props.fileCardFor ? u3(FileCard, { ...props }, "FileCard") : null }), u3(Slide_default, { children: props.activePickerPanel ? u3(PickerPanelContent_default, { ...props }, "Picker") : null }), u3(Slide_default, { children: props.showFileEditor ? u3(EditorPanel_default, { ...props }, "Editor") : null }), u3("div", { className: "uppy-Dashboard-progressindicators", children: props.progressindicators.map((target) => {
      return props.uppy.getPlugin(target.id).render(props.state);
    }) })] })] })] })
  );
  return dashboard;
}

// node_modules/@uppy/dashboard/lib/locale.js
var locale_default4 = {
  strings: {
    // When `inline: false`, used as the screen reader label for the button that closes the modal.
    closeModal: "Close Modal",
    // Used as the screen reader label for the plus (+) button that shows the “Add more files” screen
    addMoreFiles: "Add more files",
    addingMoreFiles: "Adding more files",
    // Used as the header for import panels, e.g., “Import from Google Drive”.
    importFrom: "Import from %{name}",
    // When `inline: false`, used as the screen reader label for the dashboard modal.
    dashboardWindowTitle: "Uppy Dashboard Window (Press escape to close)",
    // When `inline: true`, used as the screen reader label for the dashboard area.
    dashboardTitle: "Uppy Dashboard",
    // Shown in the Informer when a link to a file was copied to the clipboard.
    copyLinkToClipboardSuccess: "Link copied to clipboard.",
    // Used when a link cannot be copied automatically — the user has to select the text from the
    // input element below this string.
    copyLinkToClipboardFallback: "Copy the URL below",
    // Used as the hover title and screen reader label for buttons that copy a file link.
    copyLink: "Copy link",
    back: "Back",
    // Used as the screen reader label for buttons that remove a file.
    removeFile: "Remove file",
    // Used as the screen reader label for buttons that open the metadata editor panel for a file.
    editFile: "Edit file",
    editImage: "Edit image",
    // Shown in the panel header for the metadata editor. Rendered as “Editing image.png”.
    editing: "Editing %{file}",
    // Shown on the main upload screen when an upload error occurs
    error: "Error",
    // Used as the screen reader label for the button that saves metadata edits and returns to the
    // file list view.
    finishEditingFile: "Finish editing file",
    saveChanges: "Save changes",
    // Used as the label for the tab button that opens the system file selection dialog.
    myDevice: "My Device",
    dropHint: "Drop your files here",
    // Used as the hover text and screen reader label for file progress indicators when
    // they have been fully uploaded.
    uploadComplete: "Upload complete",
    uploadPaused: "Upload paused",
    // Used as the hover text and screen reader label for the buttons to resume paused uploads.
    resumeUpload: "Resume upload",
    // Used as the hover text and screen reader label for the buttons to pause uploads.
    pauseUpload: "Pause upload",
    // Used as the hover text and screen reader label for the buttons to retry failed uploads.
    retryUpload: "Retry upload",
    // Used as the hover text and screen reader label for the buttons to cancel uploads.
    cancelUpload: "Cancel upload",
    // Used in a title, how many files are currently selected
    xFilesSelected: {
      0: "%{smart_count} file selected",
      1: "%{smart_count} files selected"
    },
    uploadingXFiles: {
      0: "Uploading %{smart_count} file",
      1: "Uploading %{smart_count} files"
    },
    processingXFiles: {
      0: "Processing %{smart_count} file",
      1: "Processing %{smart_count} files"
    },
    // The "powered by Uppy" link at the bottom of the Dashboard.
    poweredBy: "Powered by %{uppy}",
    addMore: "Add more",
    editFileWithFilename: "Edit file %{file}",
    save: "Save",
    cancel: "Cancel",
    dropPasteFiles: "Drop files here or %{browseFiles}",
    dropPasteFolders: "Drop files here or %{browseFolders}",
    dropPasteBoth: "Drop files here, %{browseFiles} or %{browseFolders}",
    dropPasteImportFiles: "Drop files here, %{browseFiles} or import from:",
    dropPasteImportFolders: "Drop files here, %{browseFolders} or import from:",
    dropPasteImportBoth: "Drop files here, %{browseFiles}, %{browseFolders} or import from:",
    importFiles: "Import files from:",
    browseFiles: "browse files",
    browseFolders: "browse folders",
    recoveredXFiles: {
      0: "We could not fully recover 1 file. Please re-select it and resume the upload.",
      1: "We could not fully recover %{smart_count} files. Please re-select them and resume the upload."
    },
    recoveredAllFiles: "We restored all files. You can now resume the upload.",
    sessionRestored: "Session restored",
    reSelect: "Re-select",
    missingRequiredMetaFields: {
      0: "Missing required meta field: %{fields}.",
      1: "Missing required meta fields: %{fields}."
    },
    // Used for native device camera buttons on mobile
    takePictureBtn: "Take Picture",
    recordVideoBtn: "Record Video"
  }
};

// node_modules/@uppy/utils/lib/FOCUSABLE_ELEMENTS.js
var FOCUSABLE_ELEMENTS_default = [
  'a[href]:not([tabindex^="-"]):not([inert]):not([aria-hidden])',
  'area[href]:not([tabindex^="-"]):not([inert]):not([aria-hidden])',
  "input:not([disabled]):not([inert]):not([aria-hidden])",
  "select:not([disabled]):not([inert]):not([aria-hidden])",
  "textarea:not([disabled]):not([inert]):not([aria-hidden])",
  "button:not([disabled]):not([inert]):not([aria-hidden])",
  'iframe:not([tabindex^="-"]):not([inert]):not([aria-hidden])',
  'object:not([tabindex^="-"]):not([inert]):not([aria-hidden])',
  'embed:not([tabindex^="-"]):not([inert]):not([aria-hidden])',
  '[contenteditable]:not([tabindex^="-"]):not([inert]):not([aria-hidden])',
  '[tabindex]:not([tabindex^="-"]):not([inert]):not([aria-hidden])'
];

// node_modules/@uppy/dashboard/lib/utils/createSuperFocus.js
var import_debounce = __toESM(require_debounce(), 1);

// node_modules/@uppy/dashboard/lib/utils/getActiveOverlayEl.js
function getActiveOverlayEl(dashboardEl, activeOverlayType) {
  if (activeOverlayType) {
    const overlayEl = dashboardEl.querySelector(`[data-uppy-paneltype="${activeOverlayType}"]`);
    if (overlayEl)
      return overlayEl;
  }
  return dashboardEl;
}

// node_modules/@uppy/dashboard/lib/utils/createSuperFocus.js
function createSuperFocus() {
  let lastFocusWasOnSuperFocusableEl = false;
  const superFocus = (dashboardEl, activeOverlayType) => {
    const overlayEl = getActiveOverlayEl(dashboardEl, activeOverlayType);
    const isFocusInOverlay2 = overlayEl.contains(document.activeElement);
    if (isFocusInOverlay2 && lastFocusWasOnSuperFocusableEl)
      return;
    const superFocusableEl = overlayEl.querySelector("[data-uppy-super-focusable]");
    if (isFocusInOverlay2 && !superFocusableEl)
      return;
    if (superFocusableEl) {
      superFocusableEl.focus({ preventScroll: true });
      lastFocusWasOnSuperFocusableEl = true;
    } else {
      const firstEl = overlayEl.querySelector(FOCUSABLE_ELEMENTS_default);
      firstEl?.focus({ preventScroll: true });
      lastFocusWasOnSuperFocusableEl = false;
    }
  };
  return (0, import_debounce.default)(superFocus, 260);
}

// node_modules/@uppy/dashboard/lib/utils/trapFocus.js
function focusOnFirstNode(event, nodes) {
  const node = nodes[0];
  if (node) {
    node.focus();
    event.preventDefault();
  }
}
function focusOnLastNode(event, nodes) {
  const node = nodes[nodes.length - 1];
  if (node) {
    node.focus();
    event.preventDefault();
  }
}
function isFocusInOverlay(activeOverlayEl) {
  return activeOverlayEl.contains(document.activeElement);
}
function trapFocus(event, activeOverlayType, dashboardEl) {
  const activeOverlayEl = getActiveOverlayEl(dashboardEl, activeOverlayType);
  const focusableNodes = toArray_default(activeOverlayEl.querySelectorAll(FOCUSABLE_ELEMENTS_default));
  const focusedItemIndex = focusableNodes.indexOf(document.activeElement);
  if (!isFocusInOverlay(activeOverlayEl)) {
    focusOnFirstNode(event, focusableNodes);
  } else if (event.shiftKey && focusedItemIndex === 0) {
    focusOnLastNode(event, focusableNodes);
  } else if (!event.shiftKey && focusedItemIndex === focusableNodes.length - 1) {
    focusOnFirstNode(event, focusableNodes);
  }
}
function forInline(event, activeOverlayType, dashboardEl) {
  if (activeOverlayType === null) {
  } else {
    trapFocus(event, activeOverlayType, dashboardEl);
  }
}

// node_modules/@uppy/dashboard/lib/Dashboard.js
var TAB_KEY = 9;
var ESC_KEY = 27;
function createPromise() {
  const o4 = {};
  o4.promise = new Promise((resolve, reject) => {
    o4.resolve = resolve;
    o4.reject = reject;
  });
  return o4;
}
var defaultOptions5 = {
  target: "body",
  metaFields: [],
  thumbnailWidth: 280,
  thumbnailType: "image/jpeg",
  waitForThumbnailsBeforeUpload: false,
  defaultPickerIcon,
  showLinkToFileUploadResult: false,
  showProgressDetails: false,
  hideUploadButton: false,
  hideCancelButton: false,
  hideRetryButton: false,
  hidePauseResumeButton: false,
  hideProgressAfterFinish: false,
  note: null,
  singleFileFullScreen: true,
  disableStatusBar: false,
  disableInformer: false,
  disableThumbnailGenerator: false,
  fileManagerSelectionType: "files",
  proudlyDisplayPoweredByUppy: true,
  showSelectedFiles: true,
  showRemoveButtonAfterComplete: false,
  showNativePhotoCameraButton: false,
  showNativeVideoCameraButton: false,
  theme: "light",
  autoOpen: null,
  disabled: false,
  disableLocalFiles: false,
  nativeCameraFacingMode: "",
  onDragLeave: () => {
  },
  onDragOver: () => {
  },
  onDrop: () => {
  },
  plugins: [],
  // Dynamic default options, they have to be defined in the constructor (because
  // they require access to the `this` keyword), but we still want them to
  // appear in the default options so TS knows they'll be defined.
  doneButtonHandler: void 0,
  onRequestCloseModal: null,
  // defaultModalOptions
  inline: false,
  animateOpenClose: true,
  browserBackButtonClose: false,
  closeAfterFinish: false,
  closeModalOnClickOutside: false,
  disablePageScrollWhenModalOpen: true,
  trigger: null,
  // defaultInlineOptions
  width: 750,
  height: 550
};
var _disabledNodes, _generateLargeThumbnailIfSingleFile, _openFileEditorWhenFilesAdded, _attachRenderFunctionToTarget, _isTargetSupported, _getAcquirers, _getProgressIndicators, _getEditors, _addSpecifiedPluginsFromOptions, _autoDiscoverPlugins, _addSupportedPluginIfNoTarget, _Dashboard_instances, getStatusBarOpts_fn, getThumbnailGeneratorOpts_fn, getInformerOpts_fn, getStatusBarId_fn, getThumbnailGeneratorId_fn, getInformerId_fn;
var Dashboard2 = class extends UIPlugin_default {
  constructor(uppy, opts) {
    var _a;
    const autoOpen = opts?.autoOpen ?? null;
    super(uppy, { ...defaultOptions5, ...opts, autoOpen });
    __privateAdd(this, _Dashboard_instances);
    __privateAdd(this, _disabledNodes);
    __publicField(this, "modalName", `uppy-Dashboard-${nanoid3()}`);
    __publicField(this, "superFocus", createSuperFocus());
    __publicField(this, "ifFocusedOnUppyRecently", false);
    __publicField(this, "dashboardIsDisabled");
    __publicField(this, "savedScrollPosition");
    __publicField(this, "savedActiveElement");
    __publicField(this, "resizeObserver");
    __publicField(this, "darkModeMediaQuery");
    // Timeouts
    __publicField(this, "makeDashboardInsidesVisibleAnywayTimeout");
    __publicField(this, "removeTarget", (plugin) => {
      const pluginState = this.getPluginState();
      const newTargets = pluginState.targets.filter((target) => target.id !== plugin.id);
      this.setPluginState({
        targets: newTargets
      });
    });
    __publicField(this, "addTarget", (plugin) => {
      const callerPluginId = plugin.id || plugin.constructor.name;
      const callerPluginName = plugin.title || callerPluginId;
      const callerPluginType = plugin.type;
      if (callerPluginType !== "acquirer" && callerPluginType !== "progressindicator" && callerPluginType !== "editor") {
        const msg = "Dashboard: can only be targeted by plugins of types: acquirer, progressindicator, editor";
        this.uppy.log(msg, "error");
        return null;
      }
      const target = {
        id: callerPluginId,
        name: callerPluginName,
        type: callerPluginType
      };
      const state = this.getPluginState();
      const newTargets = state.targets.slice();
      newTargets.push(target);
      this.setPluginState({
        targets: newTargets
      });
      return this.el;
    });
    __publicField(this, "hideAllPanels", () => {
      const state = this.getPluginState();
      const update = {
        activePickerPanel: void 0,
        showAddFilesPanel: false,
        activeOverlayType: null,
        fileCardFor: null,
        showFileEditor: false
      };
      if (state.activePickerPanel === update.activePickerPanel && state.showAddFilesPanel === update.showAddFilesPanel && state.showFileEditor === update.showFileEditor && state.activeOverlayType === update.activeOverlayType) {
        return;
      }
      this.setPluginState(update);
      this.uppy.emit("dashboard:close-panel", state.activePickerPanel?.id);
    });
    __publicField(this, "showPanel", (id) => {
      const { targets } = this.getPluginState();
      const activePickerPanel = targets.find((target) => {
        return target.type === "acquirer" && target.id === id;
      });
      this.setPluginState({
        activePickerPanel,
        activeOverlayType: "PickerPanel"
      });
      this.uppy.emit("dashboard:show-panel", id);
    });
    __publicField(this, "canEditFile", (file) => {
      const { targets } = this.getPluginState();
      const editors = __privateGet(this, _getEditors).call(this, targets);
      return editors.some((target) => this.uppy.getPlugin(target.id).canEditFile(file));
    });
    __publicField(this, "openFileEditor", (file) => {
      const { targets } = this.getPluginState();
      const editors = __privateGet(this, _getEditors).call(this, targets);
      this.setPluginState({
        showFileEditor: true,
        fileCardFor: file.id || null,
        activeOverlayType: "FileEditor"
      });
      editors.forEach((editor) => {
        ;
        this.uppy.getPlugin(editor.id).selectFile(file);
      });
    });
    __publicField(this, "closeFileEditor", () => {
      const { metaFields } = this.getPluginState();
      const isMetaEditorEnabled = metaFields && metaFields.length > 0;
      if (isMetaEditorEnabled) {
        this.setPluginState({
          showFileEditor: false,
          activeOverlayType: "FileCard"
        });
      } else {
        this.setPluginState({
          showFileEditor: false,
          fileCardFor: null,
          activeOverlayType: "AddFiles"
        });
      }
    });
    __publicField(this, "saveFileEditor", () => {
      const { targets } = this.getPluginState();
      const editors = __privateGet(this, _getEditors).call(this, targets);
      editors.forEach((editor) => {
        ;
        this.uppy.getPlugin(editor.id).save();
      });
      this.closeFileEditor();
    });
    __publicField(this, "openModal", () => {
      const { promise, resolve } = createPromise();
      this.savedScrollPosition = window.pageYOffset;
      this.savedActiveElement = document.activeElement;
      if (this.opts.disablePageScrollWhenModalOpen) {
        document.body.classList.add("uppy-Dashboard-isFixed");
      }
      if (this.opts.animateOpenClose && this.getPluginState().isClosing) {
        const handler = () => {
          this.setPluginState({
            isHidden: false
          });
          this.el.removeEventListener("animationend", handler, false);
          resolve();
        };
        this.el.addEventListener("animationend", handler, false);
      } else {
        this.setPluginState({
          isHidden: false
        });
        resolve();
      }
      if (this.opts.browserBackButtonClose) {
        this.updateBrowserHistory();
      }
      document.addEventListener("keydown", this.handleKeyDownInModal);
      this.uppy.emit("dashboard:modal-open");
      return promise;
    });
    __publicField(this, "closeModal", (opts) => {
      const manualClose = opts?.manualClose ?? true;
      const { isHidden, isClosing } = this.getPluginState();
      if (isHidden || isClosing) {
        return void 0;
      }
      const { promise, resolve } = createPromise();
      if (this.opts.disablePageScrollWhenModalOpen) {
        document.body.classList.remove("uppy-Dashboard-isFixed");
      }
      if (this.opts.animateOpenClose) {
        this.setPluginState({
          isClosing: true
        });
        const handler = () => {
          this.setPluginState({
            isHidden: true,
            isClosing: false
          });
          this.superFocus.cancel();
          this.savedActiveElement.focus();
          this.el.removeEventListener("animationend", handler, false);
          resolve();
        };
        this.el.addEventListener("animationend", handler, false);
      } else {
        this.setPluginState({
          isHidden: true
        });
        this.superFocus.cancel();
        this.savedActiveElement.focus();
        resolve();
      }
      document.removeEventListener("keydown", this.handleKeyDownInModal);
      if (manualClose) {
        if (this.opts.browserBackButtonClose) {
          if (history.state?.[this.modalName]) {
            history.back();
          }
        }
      }
      this.uppy.emit("dashboard:modal-closed");
      return promise;
    });
    __publicField(this, "isModalOpen", () => {
      return !this.getPluginState().isHidden || false;
    });
    __publicField(this, "requestCloseModal", () => {
      if (this.opts.onRequestCloseModal) {
        return this.opts.onRequestCloseModal();
      }
      return this.closeModal();
    });
    __publicField(this, "setDarkModeCapability", (isDarkModeOn) => {
      const { capabilities } = this.uppy.getState();
      this.uppy.setState({
        capabilities: {
          ...capabilities,
          darkMode: isDarkModeOn
        }
      });
    });
    __publicField(this, "handleSystemDarkModeChange", (event) => {
      const isDarkModeOnNow = event.matches;
      this.uppy.log(`[Dashboard] Dark mode is ${isDarkModeOnNow ? "on" : "off"}`);
      this.setDarkModeCapability(isDarkModeOnNow);
    });
    __publicField(this, "toggleFileCard", (show, fileID) => {
      const file = this.uppy.getFile(fileID);
      if (show) {
        this.uppy.emit("dashboard:file-edit-start", file);
      } else {
        this.uppy.emit("dashboard:file-edit-complete", file);
      }
      this.setPluginState({
        fileCardFor: show ? fileID : null,
        activeOverlayType: show ? "FileCard" : null
      });
    });
    __publicField(this, "toggleAddFilesPanel", (show) => {
      this.setPluginState({
        showAddFilesPanel: show,
        activeOverlayType: show ? "AddFiles" : null
      });
    });
    __publicField(this, "addFiles", (files) => {
      const descriptors = files.map((file) => ({
        source: this.id,
        name: file.name,
        type: file.type,
        data: file,
        meta: {
          // path of the file relative to the ancestor directory the user selected.
          // e.g. 'docs/Old Prague/airbnb.pdf'
          relativePath: file.relativePath || file.webkitRelativePath || null
        }
      }));
      try {
        this.uppy.addFiles(descriptors);
      } catch (err) {
        this.uppy.log(err);
      }
    });
    // ___Why make insides of Dashboard invisible until first ResizeObserver event is emitted?
    //    ResizeOberserver doesn't emit the first resize event fast enough, users can see the jump from one .uppy-size-- to
    //    another (e.g. in Safari)
    // ___Why not apply visibility property to .uppy-Dashboard-inner?
    //    Because ideally, acc to specs, ResizeObserver should see invisible elements as of width 0. So even though applying
    //    invisibility to .uppy-Dashboard-inner works now, it may not work in the future.
    __publicField(this, "startListeningToResize", () => {
      this.resizeObserver = new ResizeObserver((entries) => {
        const uppyDashboardInnerEl = entries[0];
        const { width, height } = uppyDashboardInnerEl.contentRect;
        this.setPluginState({
          containerWidth: width,
          containerHeight: height,
          areInsidesReadyToBeVisible: true
        });
      });
      this.resizeObserver.observe(this.el.querySelector(".uppy-Dashboard-inner"));
      this.makeDashboardInsidesVisibleAnywayTimeout = setTimeout(() => {
        const pluginState = this.getPluginState();
        const isModalAndClosed = !this.opts.inline && pluginState.isHidden;
        if (
          // We might want to enable this in the future
          // if ResizeObserver hasn't yet fired,
          !pluginState.areInsidesReadyToBeVisible && // and it's not due to the modal being closed
          !isModalAndClosed
        ) {
          this.uppy.log("[Dashboard] resize event didn\u2019t fire on time: defaulted to mobile layout", "warning");
          this.setPluginState({
            areInsidesReadyToBeVisible: true
          });
        }
      }, 1e3);
    });
    __publicField(this, "stopListeningToResize", () => {
      this.resizeObserver.disconnect();
      clearTimeout(this.makeDashboardInsidesVisibleAnywayTimeout);
    });
    // Records whether we have been interacting with uppy right now,
    // which is then used to determine whether state updates should trigger a refocusing.
    __publicField(this, "recordIfFocusedOnUppyRecently", (event) => {
      if (this.el.contains(event.target)) {
        this.ifFocusedOnUppyRecently = true;
      } else {
        this.ifFocusedOnUppyRecently = false;
        this.superFocus.cancel();
      }
    });
    __publicField(this, "disableInteractiveElements", (disable) => {
      const NODES_TO_DISABLE = [
        "a[href]",
        "input:not([disabled])",
        "select:not([disabled])",
        "textarea:not([disabled])",
        "button:not([disabled])",
        '[role="button"]:not([disabled])'
      ];
      const nodesToDisable = __privateGet(this, _disabledNodes) ?? toArray_default(this.el.querySelectorAll(NODES_TO_DISABLE)).filter((node) => !node.classList.contains("uppy-Dashboard-close"));
      for (const node of nodesToDisable) {
        if (node.tagName === "A") {
          node.setAttribute("aria-disabled", disable);
        } else {
          node.disabled = disable;
        }
      }
      if (disable) {
        __privateSet(this, _disabledNodes, nodesToDisable);
      } else {
        __privateSet(this, _disabledNodes, null);
      }
      this.dashboardIsDisabled = disable;
    });
    __publicField(this, "updateBrowserHistory", () => {
      if (!history.state?.[this.modalName]) {
        history.pushState({
          ...history.state,
          [this.modalName]: true
        }, "");
      }
      window.addEventListener("popstate", this.handlePopState, false);
    });
    __publicField(this, "handlePopState", (event) => {
      if (this.isModalOpen() && (!event.state || !event.state[this.modalName])) {
        this.closeModal({ manualClose: false });
      }
      if (!this.isModalOpen() && event.state?.[this.modalName]) {
        history.back();
      }
    });
    __publicField(this, "handleKeyDownInModal", (event) => {
      if (event.keyCode === ESC_KEY)
        this.requestCloseModal();
      if (event.keyCode === TAB_KEY)
        trapFocus(event, this.getPluginState().activeOverlayType, this.el);
    });
    __publicField(this, "handleClickOutside", () => {
      if (this.opts.closeModalOnClickOutside)
        this.requestCloseModal();
    });
    __publicField(this, "handlePaste", (event) => {
      this.uppy.iteratePlugins((plugin) => {
        if (plugin.type === "acquirer") {
          ;
          plugin.handleRootPaste?.(event);
        }
      });
      const files = toArray_default(event.clipboardData.files);
      if (files.length > 0) {
        this.uppy.log("[Dashboard] Files pasted");
        this.addFiles(files);
      }
    });
    __publicField(this, "handleInputChange", (event) => {
      event.preventDefault();
      const files = toArray_default(event.currentTarget.files || []);
      if (files.length > 0) {
        this.uppy.log("[Dashboard] Files selected through input");
        this.addFiles(files);
      }
    });
    __publicField(this, "handleDragOver", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const canSomePluginHandleRootDrop = () => {
        let somePluginCanHandleRootDrop2 = true;
        this.uppy.iteratePlugins((plugin) => {
          if (plugin.canHandleRootDrop?.(event)) {
            somePluginCanHandleRootDrop2 = true;
          }
        });
        return somePluginCanHandleRootDrop2;
      };
      const doesEventHaveFiles = () => {
        const { types } = event.dataTransfer;
        return types.some((type) => type === "Files");
      };
      const somePluginCanHandleRootDrop = canSomePluginHandleRootDrop();
      const hasFiles = doesEventHaveFiles();
      if (!somePluginCanHandleRootDrop && !hasFiles || this.opts.disabled || // opts.disableLocalFiles should only be taken into account if no plugins
      // can handle the datatransfer
      this.opts.disableLocalFiles && (hasFiles || !somePluginCanHandleRootDrop) || !this.uppy.getState().allowNewUpload) {
        event.dataTransfer.dropEffect = "none";
        return;
      }
      event.dataTransfer.dropEffect = "copy";
      this.setPluginState({ isDraggingOver: true });
      this.opts.onDragOver(event);
    });
    __publicField(this, "handleDragLeave", (event) => {
      event.preventDefault();
      event.stopPropagation();
      this.setPluginState({ isDraggingOver: false });
      this.opts.onDragLeave(event);
    });
    __publicField(this, "handleDrop", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      this.setPluginState({ isDraggingOver: false });
      this.uppy.iteratePlugins((plugin) => {
        if (plugin.type === "acquirer") {
          ;
          plugin.handleRootDrop?.(event);
        }
      });
      let executedDropErrorOnce = false;
      const logDropError = (error) => {
        this.uppy.log(error, "error");
        if (!executedDropErrorOnce) {
          this.uppy.info(error.message, "error");
          executedDropErrorOnce = true;
        }
      };
      this.uppy.log("[Dashboard] Processing dropped files");
      const files = await getDroppedFiles(event.dataTransfer, { logDropError });
      if (files.length > 0) {
        this.uppy.log("[Dashboard] Files dropped");
        this.addFiles(files);
      }
      this.opts.onDrop(event);
    });
    __publicField(this, "handleRequestThumbnail", (file) => {
      if (!this.opts.waitForThumbnailsBeforeUpload) {
        this.uppy.emit("thumbnail:request", file);
      }
    });
    /**
     * We cancel thumbnail requests when a file item component unmounts to avoid
     * clogging up the queue when the user scrolls past many elements.
     */
    __publicField(this, "handleCancelThumbnail", (file) => {
      if (!this.opts.waitForThumbnailsBeforeUpload) {
        this.uppy.emit("thumbnail:cancel", file);
      }
    });
    __publicField(this, "handleKeyDownInInline", (event) => {
      if (event.keyCode === TAB_KEY)
        forInline(event, this.getPluginState().activeOverlayType, this.el);
    });
    // ___Why do we listen to the 'paste' event on a document instead of onPaste={props.handlePaste} prop,
    //    or this.el.addEventListener('paste')?
    //    Because (at least) Chrome doesn't handle paste if focus is on some button, e.g. 'My Device'.
    //    => Therefore, the best option is to listen to all 'paste' events, and only react to them when we are focused on our
    //       particular Uppy instance.
    // ___Why do we still need onPaste={props.handlePaste} for the DashboardUi?
    //    Because if we click on the 'Drop files here' caption e.g., `document.activeElement` will be 'body'. Which means our
    //    standard determination of whether we're pasting into our Uppy instance won't work.
    //    => Therefore, we need a traditional onPaste={props.handlePaste} handler too.
    __publicField(this, "handlePasteOnBody", (event) => {
      const isFocusInOverlay2 = this.el.contains(document.activeElement);
      if (isFocusInOverlay2) {
        this.handlePaste(event);
      }
    });
    __publicField(this, "handleComplete", ({ failed }) => {
      if (this.opts.closeAfterFinish && !failed?.length) {
        this.requestCloseModal();
      }
    });
    __publicField(this, "handleCancelRestore", () => {
      this.uppy.emit("restore-canceled");
    });
    __privateAdd(this, _generateLargeThumbnailIfSingleFile, () => {
      if (this.opts.disableThumbnailGenerator) {
        return;
      }
      const LARGE_THUMBNAIL = 600;
      const files = this.uppy.getFiles();
      if (files.length === 1) {
        const thumbnailGenerator = this.uppy.getPlugin(`${this.id}:ThumbnailGenerator`);
        thumbnailGenerator?.setOptions({ thumbnailWidth: LARGE_THUMBNAIL });
        const fileForThumbnail = { ...files[0], preview: void 0 };
        thumbnailGenerator?.requestThumbnail(fileForThumbnail).then(() => {
          thumbnailGenerator?.setOptions({
            thumbnailWidth: this.opts.thumbnailWidth
          });
        });
      }
    });
    __privateAdd(this, _openFileEditorWhenFilesAdded, (files) => {
      const firstFile = files[0];
      const { metaFields } = this.getPluginState();
      const isMetaEditorEnabled = metaFields && metaFields.length > 0;
      const isImageEditorEnabled = this.canEditFile(firstFile);
      if (isMetaEditorEnabled && this.opts.autoOpen === "metaEditor") {
        this.toggleFileCard(true, firstFile.id);
      } else if (isImageEditorEnabled && this.opts.autoOpen === "imageEditor") {
        this.openFileEditor(firstFile);
      }
    });
    __publicField(this, "initEvents", () => {
      if (this.opts.trigger && !this.opts.inline) {
        const showModalTrigger = findAllDOMElements_default(this.opts.trigger);
        if (showModalTrigger) {
          showModalTrigger.forEach((trigger) => trigger.addEventListener("click", this.openModal));
        } else {
          this.uppy.log("Dashboard modal trigger not found. Make sure `trigger` is set in Dashboard options, unless you are planning to call `dashboard.openModal()` method yourself", "warning");
        }
      }
      this.startListeningToResize();
      document.addEventListener("paste", this.handlePasteOnBody);
      this.uppy.on("plugin-added", __privateGet(this, _addSupportedPluginIfNoTarget));
      this.uppy.on("plugin-remove", this.removeTarget);
      this.uppy.on("file-added", this.hideAllPanels);
      this.uppy.on("dashboard:modal-closed", this.hideAllPanels);
      this.uppy.on("complete", this.handleComplete);
      this.uppy.on("files-added", __privateGet(this, _generateLargeThumbnailIfSingleFile));
      this.uppy.on("file-removed", __privateGet(this, _generateLargeThumbnailIfSingleFile));
      document.addEventListener("focus", this.recordIfFocusedOnUppyRecently, true);
      document.addEventListener("click", this.recordIfFocusedOnUppyRecently, true);
      if (this.opts.inline) {
        this.el.addEventListener("keydown", this.handleKeyDownInInline);
      }
      if (this.opts.autoOpen) {
        this.uppy.on("files-added", __privateGet(this, _openFileEditorWhenFilesAdded));
      }
    });
    __publicField(this, "removeEvents", () => {
      const showModalTrigger = findAllDOMElements_default(this.opts.trigger);
      if (!this.opts.inline && showModalTrigger) {
        showModalTrigger.forEach((trigger) => trigger.removeEventListener("click", this.openModal));
      }
      this.stopListeningToResize();
      document.removeEventListener("paste", this.handlePasteOnBody);
      window.removeEventListener("popstate", this.handlePopState, false);
      this.uppy.off("plugin-added", __privateGet(this, _addSupportedPluginIfNoTarget));
      this.uppy.off("plugin-remove", this.removeTarget);
      this.uppy.off("file-added", this.hideAllPanels);
      this.uppy.off("dashboard:modal-closed", this.hideAllPanels);
      this.uppy.off("complete", this.handleComplete);
      this.uppy.off("files-added", __privateGet(this, _generateLargeThumbnailIfSingleFile));
      this.uppy.off("file-removed", __privateGet(this, _generateLargeThumbnailIfSingleFile));
      document.removeEventListener("focus", this.recordIfFocusedOnUppyRecently);
      document.removeEventListener("click", this.recordIfFocusedOnUppyRecently);
      if (this.opts.inline) {
        this.el.removeEventListener("keydown", this.handleKeyDownInInline);
      }
      if (this.opts.autoOpen) {
        this.uppy.off("files-added", __privateGet(this, _openFileEditorWhenFilesAdded));
      }
    });
    __publicField(this, "superFocusOnEachUpdate", () => {
      const isFocusInUppy = this.el.contains(document.activeElement);
      const isFocusNowhere = document.activeElement === document.body || document.activeElement === null;
      const isInformerHidden = this.uppy.getState().info.length === 0;
      const isModal = !this.opts.inline;
      if (
        // If update is connected to showing the Informer - let the screen reader calmly read it.
        isInformerHidden && // If we are in a modal - always superfocus without concern for other elements
        // on the page (user is unlikely to want to interact with the rest of the page)
        (isModal || // If we are already inside of Uppy, or
        isFocusInUppy || // If we are not focused on anything BUT we have already, at least once, focused on uppy
        //   1. We focus when isFocusNowhere, because when the element we were focused
        //      on disappears (e.g. an overlay), - focus gets lost. If user is typing
        //      something somewhere else on the page, - focus won't be 'nowhere'.
        //   2. We only focus when focus is nowhere AND this.ifFocusedOnUppyRecently,
        //      to avoid focus jumps if we do something else on the page.
        //   [Practical check] Without '&& this.ifFocusedOnUppyRecently', in Safari, in inline mode,
        //                     when file is uploading, - navigate via tab to the checkbox,
        //                     try to press space multiple times. Focus will jump to Uppy.
        isFocusNowhere && this.ifFocusedOnUppyRecently)
      ) {
        this.superFocus(this.el, this.getPluginState().activeOverlayType);
      } else {
        this.superFocus.cancel();
      }
    });
    __publicField(this, "afterUpdate", () => {
      if (this.opts.disabled && !this.dashboardIsDisabled) {
        this.disableInteractiveElements(true);
        return;
      }
      if (!this.opts.disabled && this.dashboardIsDisabled) {
        this.disableInteractiveElements(false);
      }
      this.superFocusOnEachUpdate();
    });
    __publicField(this, "saveFileCard", (meta, fileID) => {
      this.uppy.setFileMeta(fileID, meta);
      this.toggleFileCard(false, fileID);
    });
    __privateAdd(this, _attachRenderFunctionToTarget, (target) => {
      const plugin = this.uppy.getPlugin(target.id);
      return {
        ...target,
        icon: plugin.icon || this.opts.defaultPickerIcon,
        render: plugin.render
      };
    });
    __privateAdd(this, _isTargetSupported, (target) => {
      const plugin = this.uppy.getPlugin(target.id);
      if (typeof plugin.isSupported !== "function") {
        return true;
      }
      return plugin.isSupported();
    });
    __privateAdd(this, _getAcquirers, (targets) => {
      return targets.filter((target) => target.type === "acquirer" && __privateGet(this, _isTargetSupported).call(this, target)).map(__privateGet(this, _attachRenderFunctionToTarget));
    });
    __privateAdd(this, _getProgressIndicators, (targets) => {
      return targets.filter((target) => target.type === "progressindicator").map(__privateGet(this, _attachRenderFunctionToTarget));
    });
    __privateAdd(this, _getEditors, (targets) => {
      return targets.filter((target) => target.type === "editor").map(__privateGet(this, _attachRenderFunctionToTarget));
    });
    __publicField(this, "render", (state) => {
      const pluginState = this.getPluginState();
      const { files, capabilities, allowNewUpload } = state;
      const { newFiles, uploadStartedFiles, completeFiles, erroredFiles, inProgressFiles, inProgressNotPausedFiles, processingFiles, isUploadStarted, isAllComplete, isAllPaused } = this.uppy.getObjectOfFilesPerState();
      const acquirers = __privateGet(this, _getAcquirers).call(this, pluginState.targets);
      const progressindicators = __privateGet(this, _getProgressIndicators).call(this, pluginState.targets);
      const editors = __privateGet(this, _getEditors).call(this, pluginState.targets);
      let theme;
      if (this.opts.theme === "auto") {
        theme = capabilities.darkMode ? "dark" : "light";
      } else {
        theme = this.opts.theme;
      }
      if (["files", "folders", "both"].indexOf(this.opts.fileManagerSelectionType) < 0) {
        this.opts.fileManagerSelectionType = "files";
        console.warn(`Unsupported option for "fileManagerSelectionType". Using default of "${this.opts.fileManagerSelectionType}".`);
      }
      return Dashboard({
        state,
        isHidden: pluginState.isHidden,
        files,
        newFiles,
        uploadStartedFiles,
        completeFiles,
        erroredFiles,
        inProgressFiles,
        inProgressNotPausedFiles,
        processingFiles,
        isUploadStarted,
        isAllComplete,
        isAllPaused,
        totalFileCount: Object.keys(files).length,
        totalProgress: state.totalProgress,
        allowNewUpload,
        acquirers,
        theme,
        disabled: this.opts.disabled,
        disableLocalFiles: this.opts.disableLocalFiles,
        direction: this.opts.direction,
        activePickerPanel: pluginState.activePickerPanel,
        showFileEditor: pluginState.showFileEditor,
        saveFileEditor: this.saveFileEditor,
        closeFileEditor: this.closeFileEditor,
        disableInteractiveElements: this.disableInteractiveElements,
        animateOpenClose: this.opts.animateOpenClose,
        isClosing: pluginState.isClosing,
        progressindicators,
        editors,
        autoProceed: this.uppy.opts.autoProceed,
        id: this.id,
        closeModal: this.requestCloseModal,
        handleClickOutside: this.handleClickOutside,
        handleInputChange: this.handleInputChange,
        handlePaste: this.handlePaste,
        inline: this.opts.inline,
        showPanel: this.showPanel,
        hideAllPanels: this.hideAllPanels,
        i18n: this.i18n,
        i18nArray: this.i18nArray,
        uppy: this.uppy,
        note: this.opts.note,
        recoveredState: state.recoveredState,
        metaFields: pluginState.metaFields,
        resumableUploads: capabilities.resumableUploads || false,
        individualCancellation: capabilities.individualCancellation,
        isMobileDevice: capabilities.isMobileDevice,
        fileCardFor: pluginState.fileCardFor,
        toggleFileCard: this.toggleFileCard,
        toggleAddFilesPanel: this.toggleAddFilesPanel,
        showAddFilesPanel: pluginState.showAddFilesPanel,
        saveFileCard: this.saveFileCard,
        openFileEditor: this.openFileEditor,
        canEditFile: this.canEditFile,
        width: this.opts.width,
        height: this.opts.height,
        showLinkToFileUploadResult: this.opts.showLinkToFileUploadResult,
        fileManagerSelectionType: this.opts.fileManagerSelectionType,
        proudlyDisplayPoweredByUppy: this.opts.proudlyDisplayPoweredByUppy,
        hideCancelButton: this.opts.hideCancelButton,
        hideRetryButton: this.opts.hideRetryButton,
        hidePauseResumeButton: this.opts.hidePauseResumeButton,
        showRemoveButtonAfterComplete: this.opts.showRemoveButtonAfterComplete,
        containerWidth: pluginState.containerWidth,
        containerHeight: pluginState.containerHeight,
        areInsidesReadyToBeVisible: pluginState.areInsidesReadyToBeVisible,
        parentElement: this.el,
        allowedFileTypes: this.uppy.opts.restrictions.allowedFileTypes,
        maxNumberOfFiles: this.uppy.opts.restrictions.maxNumberOfFiles,
        requiredMetaFields: this.uppy.opts.restrictions.requiredMetaFields,
        showSelectedFiles: this.opts.showSelectedFiles,
        showNativePhotoCameraButton: this.opts.showNativePhotoCameraButton,
        showNativeVideoCameraButton: this.opts.showNativeVideoCameraButton,
        nativeCameraFacingMode: this.opts.nativeCameraFacingMode,
        singleFileFullScreen: this.opts.singleFileFullScreen,
        handleCancelRestore: this.handleCancelRestore,
        handleRequestThumbnail: this.handleRequestThumbnail,
        handleCancelThumbnail: this.handleCancelThumbnail,
        // drag props
        isDraggingOver: pluginState.isDraggingOver,
        handleDragOver: this.handleDragOver,
        handleDragLeave: this.handleDragLeave,
        handleDrop: this.handleDrop
      });
    });
    __privateAdd(this, _addSpecifiedPluginsFromOptions, () => {
      const { plugins } = this.opts;
      plugins.forEach((pluginID) => {
        const plugin = this.uppy.getPlugin(pluginID);
        if (plugin) {
          ;
          plugin.mount(this, plugin);
        } else {
          this.uppy.log(`[Uppy] Dashboard could not find plugin '${pluginID}', make sure to uppy.use() the plugins you are specifying`, "warning");
        }
      });
    });
    __privateAdd(this, _autoDiscoverPlugins, () => {
      this.uppy.iteratePlugins(__privateGet(this, _addSupportedPluginIfNoTarget));
    });
    __privateAdd(this, _addSupportedPluginIfNoTarget, (plugin) => {
      const typesAllowed = ["acquirer", "editor"];
      if (plugin && !plugin.opts?.target && typesAllowed.includes(plugin.type)) {
        const pluginAlreadyAdded = this.getPluginState().targets.some((installedPlugin) => plugin.id === installedPlugin.id);
        if (!pluginAlreadyAdded) {
          ;
          plugin.mount(this, plugin);
        }
      }
    });
    __publicField(this, "install", () => {
      this.setPluginState({
        isHidden: true,
        fileCardFor: null,
        activeOverlayType: null,
        showAddFilesPanel: false,
        activePickerPanel: void 0,
        showFileEditor: false,
        metaFields: this.opts.metaFields,
        targets: [],
        // We'll make them visible once .containerWidth is determined
        areInsidesReadyToBeVisible: false,
        isDraggingOver: false
      });
      const { inline, closeAfterFinish } = this.opts;
      if (inline && closeAfterFinish) {
        throw new Error("[Dashboard] `closeAfterFinish: true` cannot be used on an inline Dashboard, because an inline Dashboard cannot be closed at all. Either set `inline: false`, or disable the `closeAfterFinish` option.");
      }
      const { allowMultipleUploads, allowMultipleUploadBatches } = this.uppy.opts;
      if ((allowMultipleUploads || allowMultipleUploadBatches) && closeAfterFinish) {
        this.uppy.log("[Dashboard] When using `closeAfterFinish`, we recommended setting the `allowMultipleUploadBatches` option to `false` in the Uppy constructor. See https://uppy.io/docs/uppy/#allowMultipleUploads-true", "warning");
      }
      const { target } = this.opts;
      if (target) {
        this.mount(target, this);
      }
      if (!this.opts.disableStatusBar) {
        this.uppy.use(StatusBar, {
          id: __privateMethod(this, _Dashboard_instances, getStatusBarId_fn).call(this),
          target: this,
          ...__privateMethod(this, _Dashboard_instances, getStatusBarOpts_fn).call(this)
        });
      }
      if (!this.opts.disableInformer) {
        this.uppy.use(Informer, {
          id: __privateMethod(this, _Dashboard_instances, getInformerId_fn).call(this),
          target: this,
          ...__privateMethod(this, _Dashboard_instances, getInformerOpts_fn).call(this)
        });
      }
      if (!this.opts.disableThumbnailGenerator) {
        this.uppy.use(ThumbnailGenerator, {
          id: __privateMethod(this, _Dashboard_instances, getThumbnailGeneratorId_fn).call(this),
          ...__privateMethod(this, _Dashboard_instances, getThumbnailGeneratorOpts_fn).call(this)
        });
      }
      this.darkModeMediaQuery = typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
      const isDarkModeOnFromTheStart = this.darkModeMediaQuery ? this.darkModeMediaQuery.matches : false;
      this.uppy.log(`[Dashboard] Dark mode is ${isDarkModeOnFromTheStart ? "on" : "off"}`);
      this.setDarkModeCapability(isDarkModeOnFromTheStart);
      if (this.opts.theme === "auto") {
        this.darkModeMediaQuery?.addListener(this.handleSystemDarkModeChange);
      }
      __privateGet(this, _addSpecifiedPluginsFromOptions).call(this);
      __privateGet(this, _autoDiscoverPlugins).call(this);
      this.initEvents();
    });
    __publicField(this, "uninstall", () => {
      if (!this.opts.disableInformer) {
        const informer = this.uppy.getPlugin(`${this.id}:Informer`);
        if (informer)
          this.uppy.removePlugin(informer);
      }
      if (!this.opts.disableStatusBar) {
        const statusBar = this.uppy.getPlugin(`${this.id}:StatusBar`);
        if (statusBar)
          this.uppy.removePlugin(statusBar);
      }
      if (!this.opts.disableThumbnailGenerator) {
        const thumbnail = this.uppy.getPlugin(`${this.id}:ThumbnailGenerator`);
        if (thumbnail)
          this.uppy.removePlugin(thumbnail);
      }
      const { plugins } = this.opts;
      plugins.forEach((pluginID) => {
        const plugin = this.uppy.getPlugin(pluginID);
        if (plugin)
          plugin.unmount();
      });
      if (this.opts.theme === "auto") {
        this.darkModeMediaQuery?.removeListener(this.handleSystemDarkModeChange);
      }
      if (this.opts.disablePageScrollWhenModalOpen) {
        document.body.classList.remove("uppy-Dashboard-isFixed");
      }
      this.unmount();
      this.removeEvents();
    });
    this.id = this.opts.id || "Dashboard";
    this.title = "Dashboard";
    this.type = "orchestrator";
    this.defaultLocale = locale_default4;
    if (this.opts.doneButtonHandler === void 0) {
      this.opts.doneButtonHandler = () => {
        this.uppy.clear();
        this.requestCloseModal();
      };
    }
    (_a = this.opts).onRequestCloseModal ?? (_a.onRequestCloseModal = () => this.closeModal());
    this.i18nInit();
  }
  setOptions(opts) {
    super.setOptions(opts);
    this.uppy.getPlugin(__privateMethod(this, _Dashboard_instances, getStatusBarId_fn).call(this))?.setOptions(__privateMethod(this, _Dashboard_instances, getStatusBarOpts_fn).call(this));
    this.uppy.getPlugin(__privateMethod(this, _Dashboard_instances, getThumbnailGeneratorId_fn).call(this))?.setOptions(__privateMethod(this, _Dashboard_instances, getThumbnailGeneratorOpts_fn).call(this));
  }
};
_disabledNodes = new WeakMap();
_generateLargeThumbnailIfSingleFile = new WeakMap();
_openFileEditorWhenFilesAdded = new WeakMap();
_attachRenderFunctionToTarget = new WeakMap();
_isTargetSupported = new WeakMap();
_getAcquirers = new WeakMap();
_getProgressIndicators = new WeakMap();
_getEditors = new WeakMap();
_addSpecifiedPluginsFromOptions = new WeakMap();
_autoDiscoverPlugins = new WeakMap();
_addSupportedPluginIfNoTarget = new WeakMap();
_Dashboard_instances = new WeakSet();
getStatusBarOpts_fn = function() {
  const { hideUploadButton, hideRetryButton, hidePauseResumeButton, hideCancelButton, showProgressDetails, hideProgressAfterFinish, locale: l4, doneButtonHandler } = this.opts;
  return {
    hideUploadButton,
    hideRetryButton,
    hidePauseResumeButton,
    hideCancelButton,
    showProgressDetails,
    hideAfterFinish: hideProgressAfterFinish,
    locale: l4,
    doneButtonHandler
  };
};
getThumbnailGeneratorOpts_fn = function() {
  const { thumbnailWidth, thumbnailHeight, thumbnailType, waitForThumbnailsBeforeUpload } = this.opts;
  return {
    thumbnailWidth,
    thumbnailHeight,
    thumbnailType,
    waitForThumbnailsBeforeUpload,
    // If we don't block on thumbnails, we can lazily generate them
    lazy: !waitForThumbnailsBeforeUpload
  };
};
getInformerOpts_fn = function() {
  return {
    // currently no options
  };
};
getStatusBarId_fn = function() {
  return `${this.id}:StatusBar`;
};
getThumbnailGeneratorId_fn = function() {
  return `${this.id}:ThumbnailGenerator`;
};
getInformerId_fn = function() {
  return `${this.id}:Informer`;
};
__publicField(Dashboard2, "VERSION", package_default7.version);

// node_modules/@uppy/utils/lib/hasProperty.js
function hasProperty(object, key) {
  return Object.hasOwn(object, key);
}

// node_modules/@uppy/utils/lib/ErrorWithCause.js
var ErrorWithCause = class extends Error {
  constructor(message, options) {
    super(message);
    __publicField(this, "isNetworkError");
    __publicField(this, "cause");
    this.cause = options?.cause;
    if (this.cause && hasProperty(this.cause, "isNetworkError")) {
      this.isNetworkError = this.cause.isNetworkError;
    } else {
      this.isNetworkError = false;
    }
  }
};
var ErrorWithCause_default = ErrorWithCause;

// node_modules/@uppy/utils/lib/NetworkError.js
var NetworkError = class extends Error {
  constructor(error, xhr = null) {
    super(`This looks like a network error, the endpoint might be blocked by an internet provider or a firewall.`);
    __publicField(this, "cause");
    __publicField(this, "isNetworkError");
    __publicField(this, "request");
    this.cause = error;
    this.isNetworkError = true;
    this.request = xhr;
  }
};
var NetworkError_default = NetworkError;

// node_modules/@uppy/utils/lib/fetchWithNetworkError.js
function fetchWithNetworkError(...options) {
  return fetch(...options).catch((err) => {
    if (err.name === "AbortError") {
      throw err;
    } else {
      throw new NetworkError_default(err);
    }
  });
}

// node_modules/@uppy/utils/lib/getSocketHost.js
function getSocketHost(url) {
  const regex = /^(?:https?:\/\/|\/\/)?(?:[^@\n]+@)?([^\n]+)/i;
  const host = regex.exec(url)?.[1];
  const socketProtocol = /^http:\/\//i.test(url) ? "ws" : "wss";
  return `${socketProtocol}://${host}`;
}

// node_modules/@uppy/utils/lib/UserFacingApiError.js
var UserFacingApiError = class extends Error {
  constructor() {
    super(...arguments);
    __publicField(this, "name", "UserFacingApiError");
  }
};
var UserFacingApiError_default = UserFacingApiError;

// node_modules/p-retry/index.js
var import_retry = __toESM(require_retry2(), 1);

// node_modules/is-network-error/index.js
var objectToString = Object.prototype.toString;
var isError = (value) => objectToString.call(value) === "[object Error]";
var errorMessages = /* @__PURE__ */ new Set([
  "network error",
  // Chrome
  "NetworkError when attempting to fetch resource.",
  // Firefox
  "The Internet connection appears to be offline.",
  // Safari 16
  "Network request failed",
  // `cross-fetch`
  "fetch failed",
  // Undici (Node.js)
  "terminated",
  // Undici (Node.js)
  " A network error occurred.",
  // Bun (WebKit)
  "Network connection lost"
  // Cloudflare Workers (fetch)
]);
function isNetworkError(error) {
  const isValid = error && isError(error) && error.name === "TypeError" && typeof error.message === "string";
  if (!isValid) {
    return false;
  }
  const { message, stack } = error;
  if (message === "Load failed" || message.startsWith("Load failed (") && message.endsWith(")")) {
    return stack === void 0 || "__sentry_captured__" in error;
  }
  if (message.startsWith("error sending request for url")) {
    return true;
  }
  if (message === "Failed to fetch" || message.startsWith("Failed to fetch (") && message.endsWith(")")) {
    return true;
  }
  return errorMessages.has(message);
}

// node_modules/p-retry/index.js
var AbortError2 = class extends Error {
  constructor(message) {
    super();
    if (message instanceof Error) {
      this.originalError = message;
      ({ message } = message);
    } else {
      this.originalError = new Error(message);
      this.originalError.stack = this.stack;
    }
    this.name = "AbortError";
    this.message = message;
  }
};
var decorateErrorWithCounts = (error, attemptNumber, options) => {
  const retriesLeft = options.retries - (attemptNumber - 1);
  error.attemptNumber = attemptNumber;
  error.retriesLeft = retriesLeft;
  return error;
};
async function pRetry(input, options) {
  return new Promise((resolve, reject) => {
    options = { ...options };
    options.onFailedAttempt ?? (options.onFailedAttempt = () => {
    });
    options.shouldRetry ?? (options.shouldRetry = () => true);
    options.retries ?? (options.retries = 10);
    const operation = import_retry.default.operation(options);
    const abortHandler = () => {
      operation.stop();
      reject(options.signal?.reason);
    };
    if (options.signal && !options.signal.aborted) {
      options.signal.addEventListener("abort", abortHandler, { once: true });
    }
    const cleanUp = () => {
      options.signal?.removeEventListener("abort", abortHandler);
      operation.stop();
    };
    operation.attempt(async (attemptNumber) => {
      try {
        const result = await input(attemptNumber);
        cleanUp();
        resolve(result);
      } catch (error) {
        try {
          if (!(error instanceof Error)) {
            throw new TypeError(`Non-error was thrown: "${error}". You should only throw errors.`);
          }
          if (error instanceof AbortError2) {
            throw error.originalError;
          }
          if (error instanceof TypeError && !isNetworkError(error)) {
            throw error;
          }
          decorateErrorWithCounts(error, attemptNumber, options);
          if (!await options.shouldRetry(error)) {
            operation.stop();
            reject(error);
          }
          await options.onFailedAttempt(error);
          if (!operation.retry(error)) {
            throw operation.mainError();
          }
        } catch (finalError) {
          decorateErrorWithCounts(finalError, attemptNumber, options);
          cleanUp();
          reject(finalError);
        }
      }
    });
  });
}

// node_modules/@uppy/companion-client/package.json
var package_default8 = {
  name: "@uppy/companion-client",
  description: "Client library for communication with Companion. Intended for use in Uppy plugins.",
  version: "4.5.2",
  license: "MIT",
  main: "lib/index.js",
  type: "module",
  scripts: {
    build: "tsc --build tsconfig.build.json",
    typecheck: "tsc --build",
    test: "vitest run --environment=jsdom --silent='passed-only'"
  },
  keywords: [
    "file uploader",
    "uppy",
    "uppy-plugin",
    "companion",
    "provider"
  ],
  homepage: "https://uppy.io",
  bugs: {
    url: "https://github.com/transloadit/uppy/issues"
  },
  repository: {
    type: "git",
    url: "git+https://github.com/transloadit/uppy.git"
  },
  files: [
    "src",
    "lib",
    "dist",
    "CHANGELOG.md"
  ],
  dependencies: {
    "@uppy/utils": "^6.2.2",
    "namespace-emitter": "^2.0.1",
    "p-retry": "^6.1.0"
  },
  devDependencies: {
    jsdom: "^26.1.0",
    typescript: "^5.8.3",
    vitest: "^3.2.4"
  },
  peerDependencies: {
    "@uppy/core": "^4.5.2"
  }
};

// node_modules/@uppy/companion-client/lib/AuthError.js
var AuthError = class extends Error {
  constructor() {
    super("Authorization required");
    __publicField(this, "isAuthError");
    this.name = "AuthError";
    this.isAuthError = true;
  }
};
var AuthError_default = AuthError;

// node_modules/@uppy/companion-client/lib/RequestClient.js
function stripSlash(url) {
  return url.replace(/\/$/, "");
}
var retryCount = 10;
var socketActivityTimeoutMs = 5 * 60 * 1e3;
var authErrorStatusCode = 401;
var HttpError = class extends Error {
  constructor({ statusCode, message }) {
    super(message);
    __publicField(this, "statusCode");
    this.name = "HttpError";
    this.statusCode = statusCode;
  }
};
async function handleJSONResponse(res) {
  if (res.status === authErrorStatusCode) {
    throw new AuthError_default();
  }
  if (res.ok) {
    return res.json();
  }
  let errMsg = `Failed request with status: ${res.status}. ${res.statusText}`;
  let errData;
  try {
    errData = await res.json();
    if (errData.message)
      errMsg = `${errMsg} message: ${errData.message}`;
    if (errData.requestId)
      errMsg = `${errMsg} request-Id: ${errData.requestId}`;
  } catch (cause) {
    throw new Error(errMsg, { cause });
  }
  if (res.status >= 400 && res.status <= 499 && errData.message) {
    throw new UserFacingApiError_default(errData.message);
  }
  throw new HttpError({ statusCode: res.status, message: errMsg });
}
function emitSocketProgress(uploader, progressData, file) {
  const { progress, bytesUploaded, bytesTotal } = progressData;
  if (progress) {
    uploader.uppy.log(`Upload progress: ${progress}`);
    uploader.uppy.emit("upload-progress", file, {
      uploadStarted: file.progress.uploadStarted ?? 0,
      bytesUploaded,
      bytesTotal
    });
  }
}
var _companionHeaders, _RequestClient_instances, getUrl_fn, _requestSocketToken, awaitRemoteFileUpload_fn;
var RequestClient = class {
  constructor(uppy, opts) {
    __privateAdd(this, _RequestClient_instances);
    __privateAdd(this, _companionHeaders);
    __publicField(this, "uppy");
    __publicField(this, "opts");
    __privateAdd(this, _requestSocketToken, async ({ file, postBody, signal }) => {
      if (file.remote?.url == null) {
        throw new Error("Cannot connect to an undefined URL");
      }
      const res = await this.post(file.remote.url, {
        ...file.remote.body,
        ...postBody
      }, { signal });
      return res.token;
    });
    this.uppy = uppy;
    this.opts = opts;
    this.onReceiveResponse = this.onReceiveResponse.bind(this);
    __privateSet(this, _companionHeaders, opts.companionHeaders);
  }
  setCompanionHeaders(headers) {
    __privateSet(this, _companionHeaders, headers);
  }
  [Symbol.for("uppy test: getCompanionHeaders")]() {
    return __privateGet(this, _companionHeaders);
  }
  get hostname() {
    const { companion } = this.uppy.getState();
    const host = this.opts.companionUrl;
    return stripSlash(companion?.[host] ? companion[host] : host);
  }
  async headers(emptyBody = false) {
    const defaultHeaders = {
      Accept: "application/json",
      ...emptyBody ? void 0 : {
        // Passing those headers on requests with no data forces browsers to first make a preflight request.
        "Content-Type": "application/json"
      }
    };
    return {
      ...defaultHeaders,
      ...__privateGet(this, _companionHeaders)
    };
  }
  onReceiveResponse(res) {
    const { headers } = res;
    const state = this.uppy.getState();
    const companion = state.companion || {};
    const host = this.opts.companionUrl;
    if (headers.has("i-am") && headers.get("i-am") !== companion[host]) {
      this.uppy.setState({
        companion: { ...companion, [host]: headers.get("i-am") }
      });
    }
  }
  async request({ path, method = "GET", data, skipPostResponse, signal }) {
    try {
      const headers = await this.headers(!data);
      const response = await fetchWithNetworkError(__privateMethod(this, _RequestClient_instances, getUrl_fn).call(this, path), {
        method,
        signal,
        headers,
        credentials: this.opts.companionCookiesRule || "same-origin",
        body: data ? JSON.stringify(data) : null
      });
      if (!skipPostResponse)
        this.onReceiveResponse(response);
      return await handleJSONResponse(response);
    } catch (err) {
      if (err.isAuthError || err.name === "UserFacingApiError" || err.name === "AbortError")
        throw err;
      throw new ErrorWithCause_default(`Could not ${method} ${__privateMethod(this, _RequestClient_instances, getUrl_fn).call(this, path)}`, {
        cause: err
      });
    }
  }
  async get(path, options) {
    return this.request({ ...options, path });
  }
  async post(path, data, options) {
    return this.request({ ...options, path, method: "POST", data });
  }
  async delete(path, data, options) {
    return this.request({ ...options, path, method: "DELETE", data });
  }
  /**
   * Remote uploading consists of two steps:
   * 1. #requestSocketToken which starts the download/upload in companion and returns a unique token for the upload.
   * Then companion will halt the upload until:
   * 2. #awaitRemoteFileUpload is called, which will open/ensure a websocket connection towards companion, with the
   * previously generated token provided. It returns a promise that will resolve/reject once the file has finished
   * uploading or is otherwise done (failed, canceled)
   */
  async uploadRemoteFile(file, reqBody, options) {
    try {
      const { signal, getQueue } = options || {};
      return await pRetry(async () => {
        const existingServerToken = this.uppy.getFile(file.id)?.serverToken;
        if (existingServerToken != null) {
          this.uppy.log(`Connecting to exiting websocket ${existingServerToken}`);
          return __privateMethod(this, _RequestClient_instances, awaitRemoteFileUpload_fn).call(this, {
            file,
            queue: getQueue(),
            signal
          });
        }
        const queueRequestSocketToken = getQueue().wrapPromiseFunction(async (...args) => {
          try {
            return await __privateGet(this, _requestSocketToken).call(this, ...args);
          } catch (outerErr) {
            if (outerErr.isAuthError)
              throw new AbortError2(outerErr);
            if (outerErr.cause == null)
              throw outerErr;
            const err = outerErr.cause;
            const isRetryableHttpError = () => [408, 409, 429, 418, 423].includes(err.statusCode) || err.statusCode >= 500 && err.statusCode <= 599 && ![501, 505].includes(err.statusCode);
            if (err.name === "HttpError" && !isRetryableHttpError())
              throw new AbortError2(err);
            throw err;
          }
        }, { priority: -1 });
        const serverToken = await queueRequestSocketToken({
          file,
          postBody: reqBody,
          signal
        }).abortOn(signal);
        if (!this.uppy.getFile(file.id))
          return void 0;
        this.uppy.setFileState(file.id, { serverToken });
        return __privateMethod(this, _RequestClient_instances, awaitRemoteFileUpload_fn).call(this, {
          file: this.uppy.getFile(file.id),
          // re-fetching file because it might have changed in the meantime
          queue: getQueue(),
          signal
        });
      }, {
        retries: retryCount,
        signal,
        onFailedAttempt: (err) => this.uppy.log(`Retrying upload due to: ${err.message}`, "warning")
      });
    } catch (err) {
      if (err.name === "AbortError") {
        return void 0;
      }
      this.uppy.emit("upload-error", file, err);
      throw err;
    }
  }
};
_companionHeaders = new WeakMap();
_RequestClient_instances = new WeakSet();
getUrl_fn = function(url) {
  if (/^(https?:|)\/\//.test(url)) {
    return url;
  }
  return `${this.hostname}/${url}`;
};
_requestSocketToken = new WeakMap();
awaitRemoteFileUpload_fn = async function({ file, queue, signal }) {
  let removeEventHandlers;
  const { capabilities } = this.uppy.getState();
  try {
    return await new Promise((resolve, reject) => {
      const token = file.serverToken;
      const host = getSocketHost(file.remote.companionUrl);
      let socket;
      let socketAbortController;
      let activityTimeout;
      let { isPaused } = file;
      const socketSend = (action, payload) => {
        if (socket == null || socket.readyState !== socket.OPEN) {
          this.uppy.log(`Cannot send "${action}" to socket ${file.id} because the socket state was ${String(socket?.readyState)}`, "warning");
          return;
        }
        socket.send(JSON.stringify({
          action,
          payload: payload ?? {}
        }));
      };
      function sendState() {
        if (!capabilities.resumableUploads)
          return;
        if (isPaused)
          socketSend("pause");
        else
          socketSend("resume");
      }
      const createWebsocket = async () => {
        if (socketAbortController)
          socketAbortController.abort();
        socketAbortController = new AbortController();
        const onFatalError = (err) => {
          this.uppy.setFileState(file.id, { serverToken: null });
          socketAbortController?.abort?.();
          reject(err);
        };
        function resetActivityTimeout() {
          clearTimeout(activityTimeout);
          if (isPaused)
            return;
          activityTimeout = setTimeout(() => onFatalError(new Error("Timeout waiting for message from Companion socket")), socketActivityTimeoutMs);
        }
        try {
          await queue.wrapPromiseFunction(async () => {
            const reconnectWebsocket = async () => new Promise((_4, rejectSocket) => {
              socket = new WebSocket(`${host}/api/${token}`);
              resetActivityTimeout();
              socket.addEventListener("close", () => {
                socket = void 0;
                rejectSocket(new Error("Socket closed unexpectedly"));
              });
              socket.addEventListener("error", (error) => {
                this.uppy.log(`Companion socket error ${JSON.stringify(error)}, closing socket`, "warning");
                socket?.close();
              });
              socket.addEventListener("open", () => {
                sendState();
              });
              socket.addEventListener("message", (e4) => {
                resetActivityTimeout();
                try {
                  const { action, payload } = JSON.parse(e4.data);
                  switch (action) {
                    case "progress": {
                      emitSocketProgress(this, payload, this.uppy.getFile(file.id));
                      break;
                    }
                    case "success": {
                      const text = payload.response?.responseText;
                      this.uppy.emit("upload-success", this.uppy.getFile(file.id), {
                        uploadURL: payload.url,
                        status: payload.response?.status ?? 200,
                        body: text ? JSON.parse(text) : void 0
                      });
                      socketAbortController?.abort?.();
                      resolve();
                      break;
                    }
                    case "error": {
                      const { message } = payload.error;
                      throw Object.assign(new Error(message), {
                        cause: payload.error
                      });
                    }
                    default:
                      this.uppy.log(`Companion socket unknown action ${action}`, "warning");
                  }
                } catch (err) {
                  onFatalError(err);
                }
              });
              const closeSocket = () => {
                this.uppy.log(`Closing socket ${file.id}`);
                clearTimeout(activityTimeout);
                if (socket)
                  socket.close();
                socket = void 0;
              };
              socketAbortController.signal.addEventListener("abort", () => {
                closeSocket();
              });
            });
            await pRetry(reconnectWebsocket, {
              retries: retryCount,
              signal: socketAbortController.signal,
              onFailedAttempt: () => {
                if (socketAbortController.signal.aborted)
                  return;
                this.uppy.log(`Retrying websocket ${file.id}`);
              }
            });
          })().abortOn(socketAbortController.signal);
        } catch (err) {
          if (socketAbortController.signal.aborted)
            return;
          onFatalError(err);
        }
      };
      const pause = (newPausedState) => {
        if (!capabilities.resumableUploads)
          return;
        isPaused = newPausedState;
        if (socket)
          sendState();
      };
      const onFileRemove = (targetFile) => {
        if (!capabilities.individualCancellation)
          return;
        if (targetFile.id !== file.id)
          return;
        socketSend("cancel");
        socketAbortController?.abort?.();
        this.uppy.log(`upload ${file.id} was removed`);
        resolve();
      };
      const onCancelAll = () => {
        socketSend("cancel");
        socketAbortController?.abort?.();
        this.uppy.log(`upload ${file.id} was canceled`);
        resolve();
      };
      const onFilePausedChange = (targetFile, newPausedState) => {
        if (targetFile?.id !== file.id)
          return;
        pause(newPausedState);
      };
      const onPauseAll = () => pause(true);
      const onResumeAll = () => pause(false);
      this.uppy.on("file-removed", onFileRemove);
      this.uppy.on("cancel-all", onCancelAll);
      this.uppy.on("upload-pause", onFilePausedChange);
      this.uppy.on("pause-all", onPauseAll);
      this.uppy.on("resume-all", onResumeAll);
      removeEventHandlers = () => {
        this.uppy.off("file-removed", onFileRemove);
        this.uppy.off("cancel-all", onCancelAll);
        this.uppy.off("upload-pause", onFilePausedChange);
        this.uppy.off("pause-all", onPauseAll);
        this.uppy.off("resume-all", onResumeAll);
      };
      signal.addEventListener("abort", () => {
        socketAbortController?.abort();
      });
      createWebsocket();
    });
  } finally {
    removeEventHandlers?.();
  }
};
__publicField(RequestClient, "VERSION", package_default8.version);

// node_modules/@uppy/core/lib/EventManager.js
var _uppy, _events;
var EventManager = class {
  constructor(uppy) {
    __privateAdd(this, _uppy);
    __privateAdd(this, _events, []);
    __privateSet(this, _uppy, uppy);
  }
  on(event, fn2) {
    __privateGet(this, _events).push([event, fn2]);
    return __privateGet(this, _uppy).on(event, fn2);
  }
  remove() {
    for (const [event, fn2] of __privateGet(this, _events).splice(0)) {
      __privateGet(this, _uppy).off(event, fn2);
    }
  }
  onFilePause(fileID, cb) {
    this.on("upload-pause", (file, isPaused) => {
      if (fileID === file?.id) {
        cb(isPaused);
      }
    });
  }
  onFileRemove(fileID, cb) {
    this.on("file-removed", (file) => {
      if (fileID === file.id)
        cb(file.id);
    });
  }
  onPause(fileID, cb) {
    this.on("upload-pause", (file, isPaused) => {
      if (fileID === file?.id) {
        cb(isPaused);
      }
    });
  }
  onRetry(fileID, cb) {
    this.on("upload-retry", (file) => {
      if (fileID === file?.id) {
        cb();
      }
    });
  }
  onRetryAll(fileID, cb) {
    this.on("retry-all", () => {
      if (!__privateGet(this, _uppy).getFile(fileID))
        return;
      cb();
    });
  }
  onPauseAll(fileID, cb) {
    this.on("pause-all", () => {
      if (!__privateGet(this, _uppy).getFile(fileID))
        return;
      cb();
    });
  }
  onCancelAll(fileID, eventHandler) {
    this.on("cancel-all", (...args) => {
      if (!__privateGet(this, _uppy).getFile(fileID))
        return;
      eventHandler(...args);
    });
  }
  onResumeAll(fileID, cb) {
    this.on("resume-all", () => {
      if (!__privateGet(this, _uppy).getFile(fileID))
        return;
      cb();
    });
  }
};
_uppy = new WeakMap();
_events = new WeakMap();

// node_modules/@uppy/utils/lib/AbortController.js
var { AbortController: AbortController2 } = globalThis;
var { AbortSignal } = globalThis;
var createAbortError = (message = "Aborted", options) => {
  const err = new DOMException(message, "AbortError");
  if (options != null && hasProperty(options, "cause")) {
    Object.defineProperty(err, "cause", {
      // @ts-expect-error TS is drunk
      __proto__: null,
      configurable: true,
      writable: true,
      value: options.cause
    });
  }
  return err;
};

// node_modules/@uppy/utils/lib/fileFilters.js
function filterNonFailedFiles(files) {
  const hasError = (file) => "error" in file && !!file.error;
  return files.filter((file) => !hasError(file));
}
function filterFilesToEmitUploadStarted(files) {
  return files.filter((file) => !file.progress?.uploadStarted || !file.isRestored);
}

// node_modules/@uppy/utils/lib/getAllowedMetaFields.js
function getAllowedMetaFields(fields, meta) {
  if (fields === true) {
    return Object.keys(meta);
  }
  if (Array.isArray(fields)) {
    return fields;
  }
  return [];
}

// node_modules/@uppy/utils/lib/RateLimitedQueue.js
function createCancelError(cause) {
  return new Error("Cancelled", { cause });
}
function abortOn(signal) {
  if (signal != null) {
    const abortPromise = () => this.abort(signal.reason);
    signal.addEventListener("abort", abortPromise, { once: true });
    const removeAbortListener = () => {
      signal.removeEventListener("abort", abortPromise);
    };
    this.then?.(removeAbortListener, removeAbortListener);
  }
  return this;
}
var _activeRequests, _queuedHandlers, _paused, _pauseTimer, _downLimit, _upperLimit, _rateLimitingTimer, _RateLimitedQueue_instances, call_fn, queueNext_fn, next_fn2, queue_fn, dequeue_fn, _resume, _increaseLimit;
var RateLimitedQueue = class {
  constructor(limit) {
    __privateAdd(this, _RateLimitedQueue_instances);
    __privateAdd(this, _activeRequests, 0);
    __privateAdd(this, _queuedHandlers, []);
    __privateAdd(this, _paused, false);
    __privateAdd(this, _pauseTimer);
    __privateAdd(this, _downLimit, 1);
    __privateAdd(this, _upperLimit);
    __privateAdd(this, _rateLimitingTimer);
    __publicField(this, "limit");
    __privateAdd(this, _resume, () => this.resume());
    __privateAdd(this, _increaseLimit, () => {
      if (__privateGet(this, _paused)) {
        __privateSet(this, _rateLimitingTimer, setTimeout(__privateGet(this, _increaseLimit), 0));
        return;
      }
      __privateSet(this, _downLimit, this.limit);
      this.limit = Math.ceil((__privateGet(this, _upperLimit) + __privateGet(this, _downLimit)) / 2);
      for (let i4 = __privateGet(this, _downLimit); i4 <= this.limit; i4++) {
        __privateMethod(this, _RateLimitedQueue_instances, queueNext_fn).call(this);
      }
      if (__privateGet(this, _upperLimit) - __privateGet(this, _downLimit) > 3) {
        __privateSet(this, _rateLimitingTimer, setTimeout(__privateGet(this, _increaseLimit), 2e3));
      } else {
        __privateSet(this, _downLimit, Math.floor(__privateGet(this, _downLimit) / 2));
      }
    });
    if (typeof limit !== "number" || limit === 0) {
      this.limit = Infinity;
    } else {
      this.limit = limit;
    }
  }
  run(fn2, queueOptions) {
    if (!__privateGet(this, _paused) && __privateGet(this, _activeRequests) < this.limit) {
      return __privateMethod(this, _RateLimitedQueue_instances, call_fn).call(this, fn2);
    }
    return __privateMethod(this, _RateLimitedQueue_instances, queue_fn).call(this, fn2, queueOptions);
  }
  wrapSyncFunction(fn2, queueOptions) {
    return (...args) => {
      const queuedRequest = this.run(() => {
        fn2(...args);
        queueMicrotask(() => queuedRequest.done());
        return () => {
        };
      }, queueOptions);
      return {
        abortOn,
        abort() {
          queuedRequest.abort();
        }
      };
    };
  }
  wrapPromiseFunction(fn2, queueOptions) {
    return (...args) => {
      let queuedRequest;
      const outerPromise = new Promise((resolve, reject) => {
        queuedRequest = this.run(() => {
          let cancelError;
          let innerPromise;
          try {
            innerPromise = Promise.resolve(fn2(...args));
          } catch (err) {
            innerPromise = Promise.reject(err);
          }
          innerPromise.then((result) => {
            if (cancelError) {
              reject(cancelError);
            } else {
              queuedRequest.done();
              resolve(result);
            }
          }, (err) => {
            if (cancelError) {
              reject(cancelError);
            } else {
              queuedRequest.done();
              reject(err);
            }
          });
          return (cause) => {
            cancelError = createCancelError(cause);
          };
        }, queueOptions);
      });
      outerPromise.abort = (cause) => {
        queuedRequest.abort(cause);
      };
      outerPromise.abortOn = abortOn;
      return outerPromise;
    };
  }
  resume() {
    __privateSet(this, _paused, false);
    clearTimeout(__privateGet(this, _pauseTimer));
    for (let i4 = 0; i4 < this.limit; i4++) {
      __privateMethod(this, _RateLimitedQueue_instances, queueNext_fn).call(this);
    }
  }
  /**
   * Freezes the queue for a while or indefinitely.
   *
   * @param {number | null } [duration] Duration for the pause to happen, in milliseconds.
   *                                    If omitted, the queue won't resume automatically.
   */
  pause(duration2 = null) {
    __privateSet(this, _paused, true);
    clearTimeout(__privateGet(this, _pauseTimer));
    if (duration2 != null) {
      __privateSet(this, _pauseTimer, setTimeout(__privateGet(this, _resume), duration2));
    }
  }
  /**
   * Pauses the queue for a duration, and lower the limit of concurrent requests
   * when the queue resumes. When the queue resumes, it tries to progressively
   * increase the limit in `this.#increaseLimit` until another call is made to
   * `this.rateLimit`.
   * Call this function when using the RateLimitedQueue for network requests and
   * the remote server responds with 429 HTTP code.
   *
   * @param {number} duration in milliseconds.
   */
  rateLimit(duration2) {
    clearTimeout(__privateGet(this, _rateLimitingTimer));
    this.pause(duration2);
    if (this.limit > 1 && Number.isFinite(this.limit)) {
      __privateSet(this, _upperLimit, this.limit - 1);
      this.limit = __privateGet(this, _downLimit);
      __privateSet(this, _rateLimitingTimer, setTimeout(__privateGet(this, _increaseLimit), duration2));
    }
  }
  get isPaused() {
    return __privateGet(this, _paused);
  }
};
_activeRequests = new WeakMap();
_queuedHandlers = new WeakMap();
_paused = new WeakMap();
_pauseTimer = new WeakMap();
_downLimit = new WeakMap();
_upperLimit = new WeakMap();
_rateLimitingTimer = new WeakMap();
_RateLimitedQueue_instances = new WeakSet();
call_fn = function(fn2) {
  __privateSet(this, _activeRequests, __privateGet(this, _activeRequests) + 1);
  let done = false;
  let cancelActive;
  try {
    cancelActive = fn2();
  } catch (err) {
    __privateSet(this, _activeRequests, __privateGet(this, _activeRequests) - 1);
    throw err;
  }
  return {
    abort: (cause) => {
      if (done)
        return;
      done = true;
      __privateSet(this, _activeRequests, __privateGet(this, _activeRequests) - 1);
      cancelActive?.(cause);
      __privateMethod(this, _RateLimitedQueue_instances, queueNext_fn).call(this);
    },
    done: () => {
      if (done)
        return;
      done = true;
      __privateSet(this, _activeRequests, __privateGet(this, _activeRequests) - 1);
      __privateMethod(this, _RateLimitedQueue_instances, queueNext_fn).call(this);
    }
  };
};
queueNext_fn = function() {
  queueMicrotask(() => __privateMethod(this, _RateLimitedQueue_instances, next_fn2).call(this));
};
next_fn2 = function() {
  if (__privateGet(this, _paused) || __privateGet(this, _activeRequests) >= this.limit) {
    return;
  }
  if (__privateGet(this, _queuedHandlers).length === 0) {
    return;
  }
  const next = __privateGet(this, _queuedHandlers).shift();
  if (next == null) {
    throw new Error("Invariant violation: next is null");
  }
  const handler = __privateMethod(this, _RateLimitedQueue_instances, call_fn).call(this, next.fn);
  next.abort = handler.abort;
  next.done = handler.done;
};
queue_fn = function(fn2, options) {
  const handler = {
    fn: fn2,
    priority: options?.priority || 0,
    abort: () => {
      __privateMethod(this, _RateLimitedQueue_instances, dequeue_fn).call(this, handler);
    },
    done: () => {
      throw new Error("Cannot mark a queued request as done: this indicates a bug");
    }
  };
  const index = __privateGet(this, _queuedHandlers).findIndex((other) => {
    return handler.priority > other.priority;
  });
  if (index === -1) {
    __privateGet(this, _queuedHandlers).push(handler);
  } else {
    __privateGet(this, _queuedHandlers).splice(index, 0, handler);
  }
  return handler;
};
dequeue_fn = function(handler) {
  const index = __privateGet(this, _queuedHandlers).indexOf(handler);
  if (index !== -1) {
    __privateGet(this, _queuedHandlers).splice(index, 1);
  }
};
_resume = new WeakMap();
_increaseLimit = new WeakMap();
var internalRateLimitedQueue = Symbol("__queue");

// node_modules/@uppy/aws-s3/package.json
var package_default9 = {
  name: "@uppy/aws-s3",
  description: "Upload to Amazon S3 with Uppy",
  version: "4.3.2",
  license: "MIT",
  main: "lib/index.js",
  type: "module",
  scripts: {
    build: "tsc --build tsconfig.build.json",
    typecheck: "tsc --build",
    test: "vitest run --environment=jsdom --silent='passed-only'"
  },
  keywords: [
    "file uploader",
    "aws s3",
    "amazon s3",
    "s3",
    "uppy",
    "uppy-plugin",
    "multipart"
  ],
  homepage: "https://uppy.io",
  bugs: {
    url: "https://github.com/transloadit/uppy/issues"
  },
  repository: {
    type: "git",
    url: "git+https://github.com/transloadit/uppy.git"
  },
  files: [
    "src",
    "lib",
    "dist",
    "CHANGELOG.md"
  ],
  dependencies: {
    "@uppy/companion-client": "^4.5.2",
    "@uppy/utils": "^6.2.2"
  },
  devDependencies: {
    "@aws-sdk/client-s3": "^3.362.0",
    "@aws-sdk/s3-request-presigner": "^3.362.0",
    "@uppy/core": "^4.5.2",
    jsdom: "^26.1.0",
    nock: "^13.1.0",
    typescript: "^5.8.3",
    vitest: "^3.2.4",
    "whatwg-fetch": "3.6.2"
  },
  peerDependencies: {
    "@uppy/core": "^4.5.2"
  }
};

// node_modules/@uppy/aws-s3/lib/createSignedURL.js
function createCanonicalRequest({ method = "PUT", CanonicalUri = "/", CanonicalQueryString = "", SignedHeaders, HashedPayload }) {
  const headerKeys = Object.keys(SignedHeaders).map((k4) => k4.toLowerCase()).sort();
  return [
    method,
    CanonicalUri,
    CanonicalQueryString,
    ...headerKeys.map((k4) => `${k4}:${SignedHeaders[k4]}`),
    "",
    headerKeys.join(";"),
    HashedPayload
  ].join("\n");
}
var ec = new TextEncoder();
var algorithm = { name: "HMAC", hash: "SHA-256" };
async function digest(data) {
  const { subtle } = globalThis.crypto;
  return subtle.digest(algorithm.hash, ec.encode(data));
}
async function generateHmacKey(secret) {
  const { subtle } = globalThis.crypto;
  return subtle.importKey("raw", typeof secret === "string" ? ec.encode(secret) : secret, algorithm, false, ["sign"]);
}
function arrayBufferToHexString(arrayBuffer) {
  const byteArray = new Uint8Array(arrayBuffer);
  let hexString = "";
  for (let i4 = 0; i4 < byteArray.length; i4++) {
    hexString += byteArray[i4].toString(16).padStart(2, "0");
  }
  return hexString;
}
async function hash(key, data) {
  const { subtle } = globalThis.crypto;
  return subtle.sign(algorithm, await generateHmacKey(key), ec.encode(data));
}
async function createSignedURL({ accountKey, accountSecret, sessionToken, bucketName, Key, Region, expires, uploadId, partNumber }) {
  const Service = "s3";
  const host = `${Service}.${Region}.amazonaws.com`;
  const CanonicalUri = `/${bucketName}/${encodeURI(Key).replace(/[;?:@&=+$,#!'()*]/g, (c4) => `%${c4.charCodeAt(0).toString(16).toUpperCase()}`)}`;
  const payload = "UNSIGNED-PAYLOAD";
  const requestDateTime = (/* @__PURE__ */ new Date()).toISOString().replace(/[-:]|\.\d+/g, "");
  const date = requestDateTime.slice(0, 8);
  const scope = `${date}/${Region}/${Service}/aws4_request`;
  const url = new URL(`https://${host}${CanonicalUri}`);
  url.searchParams.set("X-Amz-Algorithm", "AWS4-HMAC-SHA256");
  url.searchParams.set("X-Amz-Content-Sha256", payload);
  url.searchParams.set("X-Amz-Credential", `${accountKey}/${scope}`);
  url.searchParams.set("X-Amz-Date", requestDateTime);
  url.searchParams.set("X-Amz-Expires", expires);
  url.searchParams.set("X-Amz-Security-Token", sessionToken);
  url.searchParams.set("X-Amz-SignedHeaders", "host");
  if (partNumber)
    url.searchParams.set("partNumber", partNumber);
  if (uploadId)
    url.searchParams.set("uploadId", uploadId);
  url.searchParams.set("x-id", partNumber && uploadId ? "UploadPart" : "PutObject");
  const canonical = createCanonicalRequest({
    CanonicalUri,
    CanonicalQueryString: url.search.slice(1),
    SignedHeaders: {
      host
    },
    HashedPayload: payload
  });
  const hashedCanonical = arrayBufferToHexString(await digest(canonical));
  const stringToSign = [
    `AWS4-HMAC-SHA256`,
    // The algorithm used to create the hash of the canonical request.
    requestDateTime,
    // The date and time used in the credential scope.
    scope,
    // The credential scope. This restricts the resulting signature to the specified Region and service.
    hashedCanonical
    // The hash of the canonical request.
  ].join("\n");
  const kDate = await hash(`AWS4${accountSecret}`, date);
  const kRegion = await hash(kDate, Region);
  const kService = await hash(kRegion, Service);
  const kSigning = await hash(kService, "aws4_request");
  const signature = arrayBufferToHexString(await hash(kSigning, stringToSign));
  url.searchParams.set("X-Amz-Signature", signature);
  return url;
}

// node_modules/@uppy/aws-s3/lib/MultipartUploader.js
var MB = 1024 * 1024;
var defaultOptions6 = {
  getChunkSize(file) {
    return Math.ceil(file.size / 1e4);
  },
  onProgress() {
  },
  onPartComplete() {
  },
  onSuccess() {
  },
  onError(err) {
    throw err;
  }
};
function ensureInt(value) {
  if (typeof value === "string") {
    return parseInt(value, 10);
  }
  if (typeof value === "number") {
    return value;
  }
  throw new TypeError("Expected a number");
}
var pausingUploadReason = Symbol("pausing upload, not an actual error");
var _abortController2, _chunks, _chunkState, _data, _file, _uploadHasStarted, _onError, _onSuccess, _shouldUseMultipart, _isRestoring, _onReject, _maxMultipartParts, _minPartSize, _MultipartUploader_instances, initChunks_fn, createUpload_fn2, resumeUpload_fn, _onPartProgress, _onPartComplete, abortUpload_fn;
var MultipartUploader = class {
  constructor(data, options) {
    __privateAdd(this, _MultipartUploader_instances);
    __publicField(this, "options");
    __privateAdd(this, _abortController2, new AbortController2());
    __privateAdd(this, _chunks, []);
    __privateAdd(this, _chunkState, []);
    /**
     * The (un-chunked) data to upload.
     */
    __privateAdd(this, _data);
    __privateAdd(this, _file);
    __privateAdd(this, _uploadHasStarted, false);
    __privateAdd(this, _onError);
    __privateAdd(this, _onSuccess);
    __privateAdd(this, _shouldUseMultipart);
    __privateAdd(this, _isRestoring);
    __privateAdd(this, _onReject, (err) => err?.cause === pausingUploadReason ? null : __privateGet(this, _onError).call(this, err));
    __privateAdd(this, _maxMultipartParts, 1e4);
    __privateAdd(this, _minPartSize, 5 * MB);
    __privateAdd(this, _onPartProgress, (index) => (ev) => {
      if (!ev.lengthComputable)
        return;
      __privateGet(this, _chunkState)[index].uploaded = ensureInt(ev.loaded);
      const totalUploaded = __privateGet(this, _chunkState).reduce((n3, c4) => n3 + c4.uploaded, 0);
      this.options.onProgress(totalUploaded, __privateGet(this, _data).size);
    });
    __privateAdd(this, _onPartComplete, (index) => (etag) => {
      __privateGet(this, _chunks)[index] = null;
      __privateGet(this, _chunkState)[index].etag = etag;
      __privateGet(this, _chunkState)[index].done = true;
      const part = {
        PartNumber: index + 1,
        ETag: etag
      };
      this.options.onPartComplete(part);
    });
    var _a;
    this.options = {
      ...defaultOptions6,
      ...options
    };
    (_a = this.options).getChunkSize ?? (_a.getChunkSize = defaultOptions6.getChunkSize);
    __privateSet(this, _data, data);
    __privateSet(this, _file, options.file);
    __privateSet(this, _onSuccess, this.options.onSuccess);
    __privateSet(this, _onError, this.options.onError);
    __privateSet(this, _shouldUseMultipart, this.options.shouldUseMultipart);
    __privateSet(this, _isRestoring, options.uploadId && options.key);
    __privateMethod(this, _MultipartUploader_instances, initChunks_fn).call(this);
  }
  start() {
    if (__privateGet(this, _uploadHasStarted)) {
      if (!__privateGet(this, _abortController2).signal.aborted)
        __privateGet(this, _abortController2).abort(pausingUploadReason);
      __privateSet(this, _abortController2, new AbortController2());
      __privateMethod(this, _MultipartUploader_instances, resumeUpload_fn).call(this);
    } else if (__privateGet(this, _isRestoring)) {
      this.options.companionComm.restoreUploadFile(__privateGet(this, _file), {
        uploadId: this.options.uploadId,
        key: this.options.key
      });
      __privateMethod(this, _MultipartUploader_instances, resumeUpload_fn).call(this);
    } else {
      __privateMethod(this, _MultipartUploader_instances, createUpload_fn2).call(this);
    }
  }
  pause() {
    __privateGet(this, _abortController2).abort(pausingUploadReason);
    __privateSet(this, _abortController2, new AbortController2());
  }
  abort(opts) {
    if (opts?.really)
      __privateMethod(this, _MultipartUploader_instances, abortUpload_fn).call(this);
    else
      this.pause();
  }
  [Symbol.for("uppy test: getChunkState")]() {
    return __privateGet(this, _chunkState);
  }
};
_abortController2 = new WeakMap();
_chunks = new WeakMap();
_chunkState = new WeakMap();
_data = new WeakMap();
_file = new WeakMap();
_uploadHasStarted = new WeakMap();
_onError = new WeakMap();
_onSuccess = new WeakMap();
_shouldUseMultipart = new WeakMap();
_isRestoring = new WeakMap();
_onReject = new WeakMap();
_maxMultipartParts = new WeakMap();
_minPartSize = new WeakMap();
_MultipartUploader_instances = new WeakSet();
// initChunks checks the user preference for using multipart uploads (opts.shouldUseMultipart)
// and calculates the optimal part size. When using multipart part uploads every part except for the last has
// to be at least 5 MB and there can be no more than 10K parts.
// This means we sometimes need to change the preferred part size from the user in order to meet these requirements.
initChunks_fn = function() {
  const fileSize = __privateGet(this, _data).size;
  const shouldUseMultipart = typeof __privateGet(this, _shouldUseMultipart) === "function" ? __privateGet(this, _shouldUseMultipart).call(this, __privateGet(this, _file)) : Boolean(__privateGet(this, _shouldUseMultipart));
  if (shouldUseMultipart && fileSize > __privateGet(this, _minPartSize)) {
    let chunkSize = Math.max(
      this.options.getChunkSize(__privateGet(this, _data)),
      // Math.max can take undefined but TS does not think so
      __privateGet(this, _minPartSize)
    );
    let arraySize = Math.floor(fileSize / chunkSize);
    if (arraySize > __privateGet(this, _maxMultipartParts)) {
      arraySize = __privateGet(this, _maxMultipartParts);
      chunkSize = fileSize / __privateGet(this, _maxMultipartParts);
    }
    __privateSet(this, _chunks, Array(arraySize));
    for (let offset = 0, j5 = 0; offset < fileSize; offset += chunkSize, j5++) {
      const end = Math.min(fileSize, offset + chunkSize);
      const getData = () => {
        const i22 = offset;
        return __privateGet(this, _data).slice(i22, end);
      };
      __privateGet(this, _chunks)[j5] = {
        getData,
        onProgress: __privateGet(this, _onPartProgress).call(this, j5),
        onComplete: __privateGet(this, _onPartComplete).call(this, j5),
        shouldUseMultipart
      };
      if (__privateGet(this, _isRestoring)) {
        const size = offset + chunkSize > fileSize ? fileSize - offset : chunkSize;
        __privateGet(this, _chunks)[j5].setAsUploaded = () => {
          __privateGet(this, _chunks)[j5] = null;
          __privateGet(this, _chunkState)[j5].uploaded = size;
        };
      }
    }
  } else {
    __privateSet(this, _chunks, [
      {
        getData: () => __privateGet(this, _data),
        onProgress: __privateGet(this, _onPartProgress).call(this, 0),
        onComplete: __privateGet(this, _onPartComplete).call(this, 0),
        shouldUseMultipart
      }
    ]);
  }
  __privateSet(this, _chunkState, __privateGet(this, _chunks).map(() => ({ uploaded: 0 })));
};
createUpload_fn2 = function() {
  this.options.companionComm.uploadFile(__privateGet(this, _file), __privateGet(this, _chunks), __privateGet(this, _abortController2).signal).then(__privateGet(this, _onSuccess), __privateGet(this, _onReject));
  __privateSet(this, _uploadHasStarted, true);
};
resumeUpload_fn = function() {
  this.options.companionComm.resumeUploadFile(__privateGet(this, _file), __privateGet(this, _chunks), __privateGet(this, _abortController2).signal).then(__privateGet(this, _onSuccess), __privateGet(this, _onReject));
};
_onPartProgress = new WeakMap();
_onPartComplete = new WeakMap();
abortUpload_fn = function() {
  __privateGet(this, _abortController2).abort();
  this.options.companionComm.abortFileUpload(__privateGet(this, _file)).catch((err) => this.options.log(err));
};
var MultipartUploader_default = MultipartUploader;

// node_modules/@uppy/aws-s3/lib/utils.js
function throwIfAborted(signal) {
  if (signal?.aborted) {
    throw createAbortError("The operation was aborted", {
      cause: signal.reason
    });
  }
}

// node_modules/@uppy/aws-s3/lib/HTTPCommunicationQueue.js
function removeMetadataFromURL(urlString) {
  const urlObject = new URL(urlString);
  urlObject.search = "";
  urlObject.hash = "";
  return urlObject.href;
}
var _abortMultipartUpload, _cache, _createMultipartUpload, _fetchSignature, _getUploadParameters, _listParts, _previousRetryDelay, _requests, _retryDelays, _sendCompletionRequest, _setS3MultipartState, _uploadPartBytes, _getFile, _HTTPCommunicationQueue_instances, shouldRetry_fn, nonMultipartUpload_fn;
var HTTPCommunicationQueue = class {
  constructor(requests, options, setS3MultipartState, getFile) {
    __privateAdd(this, _HTTPCommunicationQueue_instances);
    __privateAdd(this, _abortMultipartUpload);
    __privateAdd(this, _cache, /* @__PURE__ */ new WeakMap());
    __privateAdd(this, _createMultipartUpload);
    __privateAdd(this, _fetchSignature);
    __privateAdd(this, _getUploadParameters);
    __privateAdd(this, _listParts);
    __privateAdd(this, _previousRetryDelay);
    __privateAdd(this, _requests);
    __privateAdd(this, _retryDelays);
    __privateAdd(this, _sendCompletionRequest);
    __privateAdd(this, _setS3MultipartState);
    __privateAdd(this, _uploadPartBytes);
    __privateAdd(this, _getFile);
    __privateSet(this, _requests, requests);
    __privateSet(this, _setS3MultipartState, setS3MultipartState);
    __privateSet(this, _getFile, getFile);
    this.setOptions(options);
  }
  setOptions(options) {
    const requests = __privateGet(this, _requests);
    if ("abortMultipartUpload" in options) {
      __privateSet(this, _abortMultipartUpload, requests.wrapPromiseFunction(options.abortMultipartUpload, { priority: 1 }));
    }
    if ("createMultipartUpload" in options) {
      __privateSet(this, _createMultipartUpload, requests.wrapPromiseFunction(options.createMultipartUpload, { priority: -1 }));
    }
    if ("signPart" in options) {
      __privateSet(this, _fetchSignature, requests.wrapPromiseFunction(options.signPart));
    }
    if ("listParts" in options) {
      __privateSet(this, _listParts, requests.wrapPromiseFunction(options.listParts));
    }
    if ("completeMultipartUpload" in options) {
      __privateSet(this, _sendCompletionRequest, requests.wrapPromiseFunction(options.completeMultipartUpload, { priority: 1 }));
    }
    if ("retryDelays" in options) {
      __privateSet(this, _retryDelays, options.retryDelays ?? []);
    }
    if ("uploadPartBytes" in options) {
      __privateSet(this, _uploadPartBytes, requests.wrapPromiseFunction(options.uploadPartBytes, { priority: Infinity }));
    }
    if ("getUploadParameters" in options) {
      __privateSet(this, _getUploadParameters, requests.wrapPromiseFunction(options.getUploadParameters));
    }
  }
  async getUploadId(file, signal) {
    let cachedResult;
    for (; ; ) {
      cachedResult = __privateGet(this, _cache).get(file.data);
      if (cachedResult == null)
        break;
      try {
        return await cachedResult;
      } catch {
      }
    }
    const promise = __privateGet(this, _createMultipartUpload).call(this, __privateGet(this, _getFile).call(this, file), signal);
    const abortPromise = () => {
      promise.abort(signal.reason);
      __privateGet(this, _cache).delete(file.data);
    };
    signal.addEventListener("abort", abortPromise, { once: true });
    __privateGet(this, _cache).set(file.data, promise);
    promise.then(async (result) => {
      signal.removeEventListener("abort", abortPromise);
      __privateGet(this, _setS3MultipartState).call(this, file, result);
      __privateGet(this, _cache).set(file.data, result);
    }, () => {
      signal.removeEventListener("abort", abortPromise);
      __privateGet(this, _cache).delete(file.data);
    });
    return promise;
  }
  async abortFileUpload(file) {
    const result = __privateGet(this, _cache).get(file.data);
    if (result == null) {
      return;
    }
    __privateGet(this, _cache).delete(file.data);
    __privateGet(this, _setS3MultipartState).call(this, file, /* @__PURE__ */ Object.create(null));
    let awaitedResult;
    try {
      awaitedResult = await result;
    } catch {
      return;
    }
    await __privateGet(this, _abortMultipartUpload).call(this, __privateGet(this, _getFile).call(this, file), awaitedResult);
  }
  async uploadFile(file, chunks2, signal) {
    throwIfAborted(signal);
    if (chunks2.length === 1 && !chunks2[0].shouldUseMultipart) {
      return __privateMethod(this, _HTTPCommunicationQueue_instances, nonMultipartUpload_fn).call(this, file, chunks2[0], signal);
    }
    const { uploadId, key } = await this.getUploadId(file, signal);
    throwIfAborted(signal);
    try {
      const parts = await Promise.all(chunks2.map((chunk, i4) => this.uploadChunk(file, i4 + 1, chunk, signal)));
      throwIfAborted(signal);
      return await __privateGet(this, _sendCompletionRequest).call(this, __privateGet(this, _getFile).call(this, file), { key, uploadId, parts, signal }, signal).abortOn(signal);
    } catch (err) {
      if (err?.cause !== pausingUploadReason && err?.name !== "AbortError") {
        this.abortFileUpload(file);
      }
      throw err;
    }
  }
  restoreUploadFile(file, uploadIdAndKey) {
    __privateGet(this, _cache).set(file.data, uploadIdAndKey);
  }
  async resumeUploadFile(file, chunks2, signal) {
    throwIfAborted(signal);
    if (chunks2.length === 1 && chunks2[0] != null && !chunks2[0].shouldUseMultipart) {
      return __privateMethod(this, _HTTPCommunicationQueue_instances, nonMultipartUpload_fn).call(this, file, chunks2[0], signal);
    }
    const { uploadId, key } = await this.getUploadId(file, signal);
    throwIfAborted(signal);
    const alreadyUploadedParts = await __privateGet(this, _listParts).call(this, __privateGet(this, _getFile).call(this, file), { uploadId, key, signal }, signal).abortOn(signal);
    throwIfAborted(signal);
    const parts = await Promise.all(chunks2.map((chunk, i4) => {
      const partNumber = i4 + 1;
      const alreadyUploadedInfo = alreadyUploadedParts.find(({ PartNumber }) => PartNumber === partNumber);
      if (alreadyUploadedInfo == null) {
        return this.uploadChunk(file, partNumber, chunk, signal);
      }
      chunk?.setAsUploaded?.();
      return { PartNumber: partNumber, ETag: alreadyUploadedInfo.ETag };
    }));
    throwIfAborted(signal);
    return __privateGet(this, _sendCompletionRequest).call(this, __privateGet(this, _getFile).call(this, file), { key, uploadId, parts, signal }, signal).abortOn(signal);
  }
  async uploadChunk(file, partNumber, chunk, signal) {
    throwIfAborted(signal);
    const { uploadId, key } = await this.getUploadId(file, signal);
    const signatureRetryIterator = __privateGet(this, _retryDelays).values();
    const chunkRetryIterator = __privateGet(this, _retryDelays).values();
    const shouldRetrySignature = () => {
      const next = signatureRetryIterator.next();
      if (next == null || next.done) {
        return null;
      }
      return next.value;
    };
    for (; ; ) {
      throwIfAborted(signal);
      const chunkData = chunk.getData();
      const { onProgress, onComplete } = chunk;
      let signature;
      try {
        signature = await __privateGet(this, _fetchSignature).call(this, __privateGet(this, _getFile).call(this, file), {
          // Always defined for multipart uploads
          uploadId,
          key,
          partNumber,
          body: chunkData,
          signal
        }).abortOn(signal);
      } catch (err) {
        const timeout = shouldRetrySignature();
        if (timeout == null || signal.aborted) {
          throw err;
        }
        await new Promise((resolve) => setTimeout(resolve, timeout));
        continue;
      }
      throwIfAborted(signal);
      try {
        return {
          PartNumber: partNumber,
          ...await __privateGet(this, _uploadPartBytes).call(this, {
            signature,
            body: chunkData,
            size: chunkData.size,
            onProgress,
            onComplete,
            signal
          }).abortOn(signal)
        };
      } catch (err) {
        if (!await __privateMethod(this, _HTTPCommunicationQueue_instances, shouldRetry_fn).call(this, err, chunkRetryIterator))
          throw err;
      }
    }
  }
};
_abortMultipartUpload = new WeakMap();
_cache = new WeakMap();
_createMultipartUpload = new WeakMap();
_fetchSignature = new WeakMap();
_getUploadParameters = new WeakMap();
_listParts = new WeakMap();
_previousRetryDelay = new WeakMap();
_requests = new WeakMap();
_retryDelays = new WeakMap();
_sendCompletionRequest = new WeakMap();
_setS3MultipartState = new WeakMap();
_uploadPartBytes = new WeakMap();
_getFile = new WeakMap();
_HTTPCommunicationQueue_instances = new WeakSet();
shouldRetry_fn = async function(err, retryDelayIterator) {
  const requests = __privateGet(this, _requests);
  const status = err?.source?.status;
  if (status == null) {
    return false;
  }
  if (status === 403 && err.message === "Request has expired") {
    if (!requests.isPaused) {
      if (requests.limit === 1 || __privateGet(this, _previousRetryDelay) == null) {
        const next = retryDelayIterator.next();
        if (next == null || next.done) {
          return false;
        }
        __privateSet(this, _previousRetryDelay, next.value);
      }
      requests.rateLimit(0);
      await new Promise((resolve) => setTimeout(resolve, __privateGet(this, _previousRetryDelay)));
    }
  } else if (status === 429) {
    if (!requests.isPaused) {
      const next = retryDelayIterator.next();
      if (next == null || next.done) {
        return false;
      }
      requests.rateLimit(next.value);
    }
  } else if (status > 400 && status < 500 && status !== 409) {
    return false;
  } else if (typeof navigator !== "undefined" && navigator.onLine === false) {
    if (!requests.isPaused) {
      requests.pause();
      window.addEventListener("online", () => {
        requests.resume();
      }, { once: true });
    }
  } else {
    const next = retryDelayIterator.next();
    if (next == null || next.done) {
      return false;
    }
    await new Promise((resolve) => setTimeout(resolve, next.value));
  }
  return true;
};
nonMultipartUpload_fn = async function(file, chunk, signal) {
  const { method = "POST", url, fields, headers } = await __privateGet(this, _getUploadParameters).call(this, __privateGet(this, _getFile).call(this, file), {
    signal
  }).abortOn(signal);
  let body;
  const data = chunk.getData();
  if (method.toUpperCase() === "POST") {
    const formData = new FormData();
    Object.entries(fields).forEach(([key2, value]) => formData.set(key2, value));
    formData.set("file", data);
    body = formData;
  } else {
    body = data;
  }
  const { onProgress, onComplete } = chunk;
  const result = await __privateGet(this, _uploadPartBytes).call(this, {
    signature: { url, headers, method },
    body,
    size: data.size,
    onProgress,
    onComplete,
    signal
  }).abortOn(signal);
  const key = fields?.key;
  __privateGet(this, _setS3MultipartState).call(this, file, { key });
  return {
    ...result,
    location: result.location ?? removeMetadataFromURL(url),
    bucket: fields?.bucket,
    key
  };
};

// node_modules/@uppy/aws-s3/lib/index.js
function assertServerError(res) {
  if (res?.error) {
    const error = new Error(res.message);
    Object.assign(error, res.error);
    throw error;
  }
  return res;
}
function getExpiry(credentials) {
  const expirationDate = credentials.Expiration;
  if (expirationDate) {
    const timeUntilExpiry = Math.floor((new Date(expirationDate) - Date.now()) / 1e3);
    if (timeUntilExpiry > 9) {
      return timeUntilExpiry;
    }
  }
  return void 0;
}
function getAllowedMetadata({ meta, allowedMetaFields, querify = false }) {
  const metaFields = allowedMetaFields ?? Object.keys(meta);
  if (!meta)
    return {};
  return Object.fromEntries(metaFields.filter((key) => meta[key] != null).map((key) => {
    const realKey = querify ? `metadata[${key}]` : key;
    const value = String(meta[key]);
    return [realKey, value];
  }));
}
var defaultOptions7 = {
  allowedMetaFields: true,
  limit: 6,
  getTemporarySecurityCredentials: false,
  shouldUseMultipart: ((file) => (file.size || 0) > 100 * 1024 * 1024),
  retryDelays: [0, 1e3, 3e3, 5e3]
};
var _companionCommunicationQueue, _client, _AwsS3Multipart_instances, setClient_fn, assertHost_fn, _cachedTemporaryCredentials, getTemporarySecurityCredentials_fn, _setS3MultipartState2, _getFile2, uploadLocalFile_fn, getCompanionClientArgs_fn, _upload, _setCompanionHeaders, _setResumableUploadsCapability, _resetResumableCapability;
var _AwsS3Multipart = class _AwsS3Multipart extends BasePlugin {
  constructor(uppy, opts) {
    super(uppy, {
      ...defaultOptions7,
      uploadPartBytes: _AwsS3Multipart.uploadPartBytes,
      createMultipartUpload: null,
      listParts: null,
      abortMultipartUpload: null,
      completeMultipartUpload: null,
      signPart: null,
      getUploadParameters: null,
      ...opts
    });
    __privateAdd(this, _AwsS3Multipart_instances);
    __privateAdd(this, _companionCommunicationQueue);
    __privateAdd(this, _client);
    __publicField(this, "requests");
    __publicField(this, "uploaderEvents");
    __publicField(this, "uploaders");
    __privateAdd(this, _cachedTemporaryCredentials);
    __privateAdd(this, _setS3MultipartState2, (file, { key, uploadId }) => {
      const cFile = this.uppy.getFile(file.id);
      if (cFile == null) {
        return;
      }
      this.uppy.setFileState(file.id, {
        s3Multipart: {
          ...cFile.s3Multipart,
          key,
          uploadId
        }
      });
    });
    __privateAdd(this, _getFile2, (file) => {
      return this.uppy.getFile(file.id) || file;
    });
    __privateAdd(this, _upload, async (fileIDs) => {
      if (fileIDs.length === 0)
        return void 0;
      const files = this.uppy.getFilesByIds(fileIDs);
      const filesFiltered = filterNonFailedFiles(files);
      const filesToEmit = filterFilesToEmitUploadStarted(filesFiltered);
      this.uppy.emit("upload-start", filesToEmit);
      const promises = filesFiltered.map((file) => {
        if (file.isRemote) {
          const getQueue = () => this.requests;
          __privateGet(this, _setResumableUploadsCapability).call(this, false);
          const controller = new AbortController();
          const removedHandler = (removedFile) => {
            if (removedFile.id === file.id)
              controller.abort();
          };
          this.uppy.on("file-removed", removedHandler);
          const uploadPromise = this.uppy.getRequestClientForFile(file).uploadRemoteFile(file, __privateMethod(this, _AwsS3Multipart_instances, getCompanionClientArgs_fn).call(this, file), {
            signal: controller.signal,
            getQueue
          });
          this.requests.wrapSyncFunction(() => {
            this.uppy.off("file-removed", removedHandler);
          }, { priority: -1 })();
          return uploadPromise;
        }
        return __privateMethod(this, _AwsS3Multipart_instances, uploadLocalFile_fn).call(this, file);
      });
      const upload = await Promise.allSettled(promises);
      __privateGet(this, _setResumableUploadsCapability).call(this, true);
      return upload;
    });
    __privateAdd(this, _setCompanionHeaders, () => {
      __privateGet(this, _client)?.setCompanionHeaders(this.opts.headers);
    });
    __privateAdd(this, _setResumableUploadsCapability, (boolean) => {
      const { capabilities } = this.uppy.getState();
      this.uppy.setState({
        capabilities: {
          ...capabilities,
          resumableUploads: boolean
        }
      });
    });
    __privateAdd(this, _resetResumableCapability, () => {
      __privateGet(this, _setResumableUploadsCapability).call(this, true);
    });
    this.type = "uploader";
    this.id = this.opts.id || "AwsS3Multipart";
    __privateMethod(this, _AwsS3Multipart_instances, setClient_fn).call(this, opts);
    const dynamicDefaultOptions = {
      createMultipartUpload: this.createMultipartUpload,
      listParts: this.listParts,
      abortMultipartUpload: this.abortMultipartUpload,
      completeMultipartUpload: this.completeMultipartUpload,
      signPart: opts?.getTemporarySecurityCredentials ? this.createSignedURL : this.signPart,
      getUploadParameters: opts?.getTemporarySecurityCredentials ? this.createSignedURL : this.getUploadParameters
    };
    for (const key of Object.keys(dynamicDefaultOptions)) {
      if (this.opts[key] == null) {
        this.opts[key] = dynamicDefaultOptions[key].bind(this);
      }
    }
    this.requests = this.opts.rateLimitedQueue ?? new RateLimitedQueue(this.opts.limit);
    __privateSet(this, _companionCommunicationQueue, new HTTPCommunicationQueue(this.requests, this.opts, __privateGet(this, _setS3MultipartState2), __privateGet(this, _getFile2)));
    this.uploaders = /* @__PURE__ */ Object.create(null);
    this.uploaderEvents = /* @__PURE__ */ Object.create(null);
  }
  [Symbol.for("uppy test: getClient")]() {
    return __privateGet(this, _client);
  }
  setOptions(newOptions) {
    __privateGet(this, _companionCommunicationQueue).setOptions(newOptions);
    super.setOptions(newOptions);
    __privateMethod(this, _AwsS3Multipart_instances, setClient_fn).call(this, newOptions);
  }
  /**
   * Clean up all references for a file's upload: the MultipartUploader instance,
   * any events related to the file, and the Companion WebSocket connection.
   *
   * Set `opts.abort` to tell S3 that the multipart upload is cancelled and must be removed.
   * This should be done when the user cancels the upload, not when the upload is completed or errored.
   */
  resetUploaderReferences(fileID, opts) {
    if (this.uploaders[fileID]) {
      this.uploaders[fileID].abort({ really: opts?.abort || false });
      this.uploaders[fileID] = null;
    }
    if (this.uploaderEvents[fileID]) {
      this.uploaderEvents[fileID].remove();
      this.uploaderEvents[fileID] = null;
    }
  }
  createMultipartUpload(file, signal) {
    __privateMethod(this, _AwsS3Multipart_instances, assertHost_fn).call(this, "createMultipartUpload");
    throwIfAborted(signal);
    const allowedMetaFields = getAllowedMetaFields(this.opts.allowedMetaFields, file.meta);
    const metadata = getAllowedMetadata({ meta: file.meta, allowedMetaFields });
    return __privateGet(this, _client).post("s3/multipart", {
      filename: file.name,
      type: file.type,
      metadata
    }, { signal }).then(assertServerError);
  }
  listParts(file, { key, uploadId, signal }, oldSignal) {
    signal ?? (signal = oldSignal);
    __privateMethod(this, _AwsS3Multipart_instances, assertHost_fn).call(this, "listParts");
    throwIfAborted(signal);
    const filename = encodeURIComponent(key);
    return __privateGet(this, _client).get(`s3/multipart/${encodeURIComponent(uploadId)}?key=${filename}`, { signal }).then(assertServerError);
  }
  completeMultipartUpload(file, { key, uploadId, parts, signal }, oldSignal) {
    signal ?? (signal = oldSignal);
    __privateMethod(this, _AwsS3Multipart_instances, assertHost_fn).call(this, "completeMultipartUpload");
    throwIfAborted(signal);
    const filename = encodeURIComponent(key);
    const uploadIdEnc = encodeURIComponent(uploadId);
    return __privateGet(this, _client).post(`s3/multipart/${uploadIdEnc}/complete?key=${filename}`, { parts: parts.map(({ ETag, PartNumber }) => ({ ETag, PartNumber })) }, { signal }).then(assertServerError);
  }
  async createSignedURL(file, options) {
    const data = await __privateMethod(this, _AwsS3Multipart_instances, getTemporarySecurityCredentials_fn).call(this, options);
    const expires = getExpiry(data.credentials) || 604800;
    const { uploadId, key, partNumber } = options;
    return {
      method: "PUT",
      expires,
      fields: {},
      url: `${await createSignedURL({
        accountKey: data.credentials.AccessKeyId,
        accountSecret: data.credentials.SecretAccessKey,
        sessionToken: data.credentials.SessionToken,
        expires,
        bucketName: data.bucket,
        Region: data.region,
        Key: key ?? `${crypto.randomUUID()}-${file.name}`,
        uploadId,
        partNumber
      })}`,
      // Provide content type header required by S3
      headers: {
        "Content-Type": file.type
      }
    };
  }
  signPart(file, { uploadId, key, partNumber, signal }) {
    __privateMethod(this, _AwsS3Multipart_instances, assertHost_fn).call(this, "signPart");
    throwIfAborted(signal);
    if (uploadId == null || key == null || partNumber == null) {
      throw new Error("Cannot sign without a key, an uploadId, and a partNumber");
    }
    const filename = encodeURIComponent(key);
    return __privateGet(this, _client).get(`s3/multipart/${encodeURIComponent(uploadId)}/${partNumber}?key=${filename}`, { signal }).then(assertServerError);
  }
  abortMultipartUpload(file, { key, uploadId, signal }) {
    __privateMethod(this, _AwsS3Multipart_instances, assertHost_fn).call(this, "abortMultipartUpload");
    const filename = encodeURIComponent(key);
    const uploadIdEnc = encodeURIComponent(uploadId);
    return __privateGet(this, _client).delete(`s3/multipart/${uploadIdEnc}?key=${filename}`, void 0, {
      signal
    }).then(assertServerError);
  }
  getUploadParameters(file, options) {
    __privateMethod(this, _AwsS3Multipart_instances, assertHost_fn).call(this, "getUploadParameters");
    const { meta } = file;
    const { type, name: filename } = meta;
    const allowedMetaFields = getAllowedMetaFields(this.opts.allowedMetaFields, file.meta);
    const metadata = getAllowedMetadata({
      meta,
      allowedMetaFields,
      querify: true
    });
    const query = new URLSearchParams({ filename, type, ...metadata });
    return __privateGet(this, _client).get(`s3/params?${query}`, options);
  }
  static async uploadPartBytes({ signature: { url, expires, headers, method = "PUT" }, body, size = body.size, onProgress, onComplete, signal }) {
    throwIfAborted(signal);
    if (url == null) {
      throw new Error("Cannot upload to an undefined URL");
    }
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open(method, url, true);
      if (headers) {
        Object.keys(headers).forEach((key) => {
          xhr.setRequestHeader(key, headers[key]);
        });
      }
      xhr.responseType = "text";
      if (typeof expires === "number") {
        xhr.timeout = expires * 1e3;
      }
      function onabort() {
        xhr.abort();
      }
      function cleanup() {
        signal?.removeEventListener("abort", onabort);
      }
      signal?.addEventListener("abort", onabort);
      xhr.upload.addEventListener("progress", (ev) => {
        onProgress(ev);
      });
      xhr.addEventListener("abort", () => {
        cleanup();
        reject(createAbortError());
      });
      xhr.addEventListener("timeout", () => {
        cleanup();
        const error = new Error("Request has expired");
        error.source = { status: 403 };
        reject(error);
      });
      xhr.addEventListener("load", () => {
        cleanup();
        if (xhr.status === 403 && xhr.responseText.includes("<Message>Request has expired</Message>")) {
          const error = new Error("Request has expired");
          error.source = xhr;
          reject(error);
          return;
        }
        if (xhr.status < 200 || xhr.status >= 300) {
          const error = new Error("Non 2xx");
          error.source = xhr;
          reject(error);
          return;
        }
        onProgress?.({ loaded: size, lengthComputable: true });
        const arr = xhr.getAllResponseHeaders().trim().split(/[\r\n]+/);
        const headersMap = { __proto__: null };
        for (const line of arr) {
          const parts = line.split(": ");
          const header = parts.shift();
          const value = parts.join(": ");
          headersMap[header] = value;
        }
        const { etag, location: location2 } = headersMap;
        if (method.toUpperCase() === "POST" && location2 == null) {
          console.error("@uppy/aws-s3: Could not read the Location header. This likely means CORS is not configured correctly on the S3 Bucket. See https://uppy.io/docs/aws-s3/#setting-up-your-s3-bucket");
        }
        if (etag == null) {
          console.error("@uppy/aws-s3: Could not read the ETag header. This likely means CORS is not configured correctly on the S3 Bucket. See https://uppy.io/docs/aws-s3/#setting-up-your-s3-bucket");
          return;
        }
        onComplete?.(etag);
        resolve({
          ...headersMap,
          ETag: etag
          // keep capitalised ETag for backwards compatiblity
        });
      });
      xhr.addEventListener("error", (ev) => {
        cleanup();
        const error = new Error("Unknown error");
        error.source = ev.target;
        reject(error);
      });
      xhr.send(body);
    });
  }
  install() {
    __privateGet(this, _setResumableUploadsCapability).call(this, true);
    this.uppy.addPreProcessor(__privateGet(this, _setCompanionHeaders));
    this.uppy.addUploader(__privateGet(this, _upload));
    this.uppy.on("cancel-all", __privateGet(this, _resetResumableCapability));
  }
  uninstall() {
    this.uppy.removePreProcessor(__privateGet(this, _setCompanionHeaders));
    this.uppy.removeUploader(__privateGet(this, _upload));
    this.uppy.off("cancel-all", __privateGet(this, _resetResumableCapability));
  }
};
_companionCommunicationQueue = new WeakMap();
_client = new WeakMap();
_AwsS3Multipart_instances = new WeakSet();
setClient_fn = function(opts) {
  if (opts == null || !("endpoint" in opts || "companionUrl" in opts || "headers" in opts || "companionHeaders" in opts || "cookiesRule" in opts || "companionCookiesRule" in opts))
    return;
  if ("companionUrl" in opts && !("endpoint" in opts)) {
    this.uppy.log("`companionUrl` option has been removed in @uppy/aws-s3, use `endpoint` instead.", "warning");
  }
  if ("companionHeaders" in opts && !("headers" in opts)) {
    this.uppy.log("`companionHeaders` option has been removed in @uppy/aws-s3, use `headers` instead.", "warning");
  }
  if ("companionCookiesRule" in opts && !("cookiesRule" in opts)) {
    this.uppy.log("`companionCookiesRule` option has been removed in @uppy/aws-s3, use `cookiesRule` instead.", "warning");
  }
  if ("endpoint" in opts) {
    __privateSet(this, _client, new RequestClient(this.uppy, {
      pluginId: this.id,
      provider: "AWS",
      companionUrl: this.opts.endpoint,
      companionHeaders: this.opts.headers,
      companionCookiesRule: this.opts.cookiesRule
    }));
  } else {
    if ("headers" in opts) {
      __privateGet(this, _setCompanionHeaders).call(this);
    }
    if ("cookiesRule" in opts) {
      __privateGet(this, _client).opts.companionCookiesRule = opts.cookiesRule;
    }
  }
};
assertHost_fn = function(method) {
  if (!__privateGet(this, _client)) {
    throw new Error(`Expected a \`endpoint\` option containing a URL, or if you are not using Companion, a custom \`${method}\` implementation.`);
  }
};
_cachedTemporaryCredentials = new WeakMap();
getTemporarySecurityCredentials_fn = async function(options) {
  throwIfAborted(options?.signal);
  if (__privateGet(this, _cachedTemporaryCredentials) == null) {
    const { getTemporarySecurityCredentials } = this.opts;
    if (getTemporarySecurityCredentials === true) {
      __privateMethod(this, _AwsS3Multipart_instances, assertHost_fn).call(this, "getTemporarySecurityCredentials");
      __privateSet(this, _cachedTemporaryCredentials, __privateGet(this, _client).get("s3/sts", options).then(assertServerError));
    } else {
      __privateSet(this, _cachedTemporaryCredentials, getTemporarySecurityCredentials(options));
    }
    __privateSet(this, _cachedTemporaryCredentials, await __privateGet(this, _cachedTemporaryCredentials));
    setTimeout(() => {
      __privateSet(this, _cachedTemporaryCredentials, null);
    }, (getExpiry(__privateGet(this, _cachedTemporaryCredentials).credentials) || 0) * 500);
  }
  return __privateGet(this, _cachedTemporaryCredentials);
};
_setS3MultipartState2 = new WeakMap();
_getFile2 = new WeakMap();
uploadLocalFile_fn = function(file) {
  return new Promise((resolve, reject) => {
    const onProgress = (bytesUploaded, bytesTotal) => {
      const latestFile = this.uppy.getFile(file.id);
      this.uppy.emit("upload-progress", latestFile, {
        uploadStarted: latestFile.progress.uploadStarted ?? 0,
        bytesUploaded,
        bytesTotal
      });
    };
    const onError = (err) => {
      this.uppy.log(err);
      this.uppy.emit("upload-error", file, err);
      this.resetUploaderReferences(file.id);
      reject(err);
    };
    const onSuccess = (result) => {
      const uploadResp = {
        body: {
          ...result
        },
        status: 200,
        uploadURL: result.location
      };
      this.resetUploaderReferences(file.id);
      this.uppy.emit("upload-success", __privateGet(this, _getFile2).call(this, file), uploadResp);
      if (result.location) {
        this.uppy.log(`Download ${file.name} from ${result.location}`);
      }
      resolve(void 0);
    };
    const upload = new MultipartUploader_default(file.data, {
      // .bind to pass the file object to each handler.
      companionComm: __privateGet(this, _companionCommunicationQueue),
      log: (...args) => this.uppy.log(...args),
      getChunkSize: this.opts.getChunkSize ? this.opts.getChunkSize.bind(this) : void 0,
      onProgress,
      onError,
      onSuccess,
      onPartComplete: (part) => {
        this.uppy.emit("s3-multipart:part-uploaded", __privateGet(this, _getFile2).call(this, file), part);
      },
      file,
      shouldUseMultipart: this.opts.shouldUseMultipart,
      ...file.s3Multipart
    });
    this.uploaders[file.id] = upload;
    const eventManager = new EventManager(this.uppy);
    this.uploaderEvents[file.id] = eventManager;
    eventManager.onFileRemove(file.id, (removed) => {
      upload.abort();
      this.resetUploaderReferences(file.id, { abort: true });
      resolve(`upload ${removed} was removed`);
    });
    eventManager.onCancelAll(file.id, () => {
      upload.abort();
      this.resetUploaderReferences(file.id, { abort: true });
      resolve(`upload ${file.id} was canceled`);
    });
    eventManager.onFilePause(file.id, (isPaused) => {
      if (isPaused) {
        upload.pause();
      } else {
        upload.start();
      }
    });
    eventManager.onPauseAll(file.id, () => {
      upload.pause();
    });
    eventManager.onResumeAll(file.id, () => {
      upload.start();
    });
    upload.start();
  });
};
getCompanionClientArgs_fn = function(file) {
  return {
    ...file.remote?.body,
    protocol: "s3-multipart",
    size: file.data.size,
    metadata: file.meta
  };
};
_upload = new WeakMap();
_setCompanionHeaders = new WeakMap();
_setResumableUploadsCapability = new WeakMap();
_resetResumableCapability = new WeakMap();
__publicField(_AwsS3Multipart, "VERSION", package_default9.version);
var AwsS3Multipart = _AwsS3Multipart;
export {
  AwsS3Multipart as AwsS3,
  Dashboard2 as Dashboard,
  Uppy_default as Uppy
};
/*! Bundled license information:

classnames/index.js:
  (*!
  	Copyright (c) 2018 Jed Watson.
  	Licensed under the MIT License (MIT), see
  	http://jedwatson.github.io/classnames
  *)

@uppy/utils/lib/Translator.js:
  (**
   * Takes a string with placeholder variables like `%{smart_count} file selected`
   * and replaces it with values from options `{smart_count: 5}`
   *
   * @license https://github.com/airbnb/polyglot.js/blob/master/LICENSE
   * taken from https://github.com/airbnb/polyglot.js/blob/master/lib/polyglot.js#L299
   *
   * @param phrase that needs interpolation, with placeholders
   * @param options with values that will be used to replace placeholders
   *)
*/
