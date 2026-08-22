/**
 * 平台扩展：字符串（作品内 ID `wpmStringV1`）
 *
 * 写法遵循 TurboWarp **沙箱**格式（`class` + `getInfo()` + `Scratch.extensions.register`），
 * 与 LLK 15.0.1 的 worker 协议同形，同时保持向 TW / Gandi 迁移的可能。
 *
 * ## 版本号写在 ID 里，这不是笔误
 *
 * `.sb3` 里**只记扩展 ID，不记它从哪儿加载**（`scratch-vm/src/serialization/sb3.js:355`
 * 官方注释写着"将来若支持按 URL 加载…"，即现在不支持；`extensionURLs` 那个 Map
 * 建出来就是空的）。所以重开作品时 VM 会拿 ID 当相对路径去 `importScripts`——
 * 实测请求的正是 `<Studio base>/wpmStringV1`。
 *
 * 于是：**ID 即路径**。把版本写进 ID，老作品的积木前缀就是老 ID，天然指向老脚本；
 * 升级发 `wpmStringV2` 并且**永不删除**老文件，历史作品就永远打得开。这条从
 * "靠纪律"变成了"结构上跑不掉"。
 *
 * ## 能力边界
 *
 * 纯字符串计算，不联网、不碰设备、不读写浏览器存储。`Scratch.Cast` 由平台垫片
 * （`_shim.js`）提供，不是 LLK 原生的。
 */

/* eslint-env worker */
/* global Scratch */

class WpmStringV1 {
    getInfo () {
        return {
            id: 'wpmStringV1',
            name: '字符串',
            color1: '#2f806e',
            color2: '#276a5c',
            color3: '#1f564a',
            blocks: [
                {
                    opcode: 'length',
                    blockType: Scratch.BlockType.REPORTER,
                    text: '[TEXT] 的长度',
                    arguments: {
                        TEXT: {type: Scratch.ArgumentType.STRING, defaultValue: '你好世界'}
                    }
                },
                {
                    opcode: 'charAt',
                    blockType: Scratch.BlockType.REPORTER,
                    text: '[TEXT] 的第 [INDEX] 个字',
                    arguments: {
                        TEXT: {type: Scratch.ArgumentType.STRING, defaultValue: '你好世界'},
                        INDEX: {type: Scratch.ArgumentType.NUMBER, defaultValue: 1}
                    }
                },
                {
                    opcode: 'substring',
                    blockType: Scratch.BlockType.REPORTER,
                    text: '[TEXT] 从第 [FROM] 个到第 [TO] 个',
                    arguments: {
                        TEXT: {type: Scratch.ArgumentType.STRING, defaultValue: '你好世界'},
                        FROM: {type: Scratch.ArgumentType.NUMBER, defaultValue: 1},
                        TO: {type: Scratch.ArgumentType.NUMBER, defaultValue: 2}
                    }
                },
                {
                    opcode: 'replaceAll',
                    blockType: Scratch.BlockType.REPORTER,
                    text: '把 [TEXT] 里的 [FROM] 换成 [TO]',
                    arguments: {
                        TEXT: {type: Scratch.ArgumentType.STRING, defaultValue: '你好世界'},
                        FROM: {type: Scratch.ArgumentType.STRING, defaultValue: '世界'},
                        TO: {type: Scratch.ArgumentType.STRING, defaultValue: '同学'}
                    }
                },
                {
                    opcode: 'indexOf',
                    blockType: Scratch.BlockType.REPORTER,
                    text: '[SUB] 在 [TEXT] 中第一次出现的位置',
                    arguments: {
                        TEXT: {type: Scratch.ArgumentType.STRING, defaultValue: '你好世界'},
                        SUB: {type: Scratch.ArgumentType.STRING, defaultValue: '世'}
                    }
                },
                {
                    opcode: 'contains',
                    blockType: Scratch.BlockType.BOOLEAN,
                    text: '[TEXT] 包含 [SUB] 吗',
                    arguments: {
                        TEXT: {type: Scratch.ArgumentType.STRING, defaultValue: '你好世界'},
                        SUB: {type: Scratch.ArgumentType.STRING, defaultValue: '世'}
                    }
                },
                {
                    opcode: 'changeCase',
                    blockType: Scratch.BlockType.REPORTER,
                    text: '把 [TEXT] 变成 [CASE]',
                    arguments: {
                        TEXT: {type: Scratch.ArgumentType.STRING, defaultValue: 'Hello'},
                        CASE: {type: Scratch.ArgumentType.STRING, menu: 'caseMenu'}
                    }
                },
                {
                    opcode: 'trim',
                    blockType: Scratch.BlockType.REPORTER,
                    text: '去掉 [TEXT] 两端的空格',
                    arguments: {
                        TEXT: {type: Scratch.ArgumentType.STRING, defaultValue: '  你好  '}
                    }
                },
                {
                    opcode: 'splitPart',
                    blockType: Scratch.BlockType.REPORTER,
                    text: '用 [SEP] 分开 [TEXT] 取第 [INDEX] 段',
                    arguments: {
                        TEXT: {type: Scratch.ArgumentType.STRING, defaultValue: '苹果,香蕉,橘子'},
                        SEP: {type: Scratch.ArgumentType.STRING, defaultValue: ','},
                        INDEX: {type: Scratch.ArgumentType.NUMBER, defaultValue: 2}
                    }
                },
                {
                    opcode: 'partCount',
                    blockType: Scratch.BlockType.REPORTER,
                    text: '用 [SEP] 分开 [TEXT] 共有几段',
                    arguments: {
                        TEXT: {type: Scratch.ArgumentType.STRING, defaultValue: '苹果,香蕉,橘子'},
                        SEP: {type: Scratch.ArgumentType.STRING, defaultValue: ','}
                    }
                }
            ],
            menus: {
                caseMenu: {
                    acceptReporters: false,
                    items: [
                        {text: '大写', value: 'upper'},
                        {text: '小写', value: 'lower'}
                    ]
                }
            }
        };
    }

    // —— 以下一律用 Array.from 按“字”切，不用 String.length ——
    // 中文是 BMP 内单码元，但 emoji 是代理对：`'👍'.length === 2`。小孩的作品里
    // emoji 很常见，按码元切会把一个表情劈成两个乱码。Array.from 按码点切，
    // “第 1 个字”拿到的才是学生眼里的那一个字。
    _chars (text) {
        return Array.from(Scratch.Cast.toString(text));
    }

    length (args) {
        return this._chars(args.TEXT).length;
    }

    charAt (args) {
        const chars = this._chars(args.TEXT);
        // Scratch 里位置从 1 开始；越界返回空字符串而不是报错（与官方"字符"积木一致）
        const index = Math.round(Scratch.Cast.toNumber(args.INDEX));
        if (index < 1 || index > chars.length) return '';
        return chars[index - 1];
    }

    substring (args) {
        const chars = this._chars(args.TEXT);
        let from = Math.round(Scratch.Cast.toNumber(args.FROM));
        let to = Math.round(Scratch.Cast.toNumber(args.TO));
        // 学生把起止写反是常事，替他兜住，不返回空
        if (from > to) {
            const swap = from;
            from = to;
            to = swap;
        }
        if (from < 1) from = 1;
        if (to > chars.length) to = chars.length;
        if (from > chars.length) return '';
        return chars.slice(from - 1, to).join('');
    }

    replaceAll (args) {
        const text = Scratch.Cast.toString(args.TEXT);
        const from = Scratch.Cast.toString(args.FROM);
        const to = Scratch.Cast.toString(args.TO);
        // 空串会让 split('') 逐字拆开再拼，等于把 TO 插进每个字之间——直接返回原文
        if (from === '') return text;
        return text.split(from).join(to);
    }

    indexOf (args) {
        const chars = this._chars(args.TEXT);
        const sub = Scratch.Cast.toString(args.SUB);
        if (sub === '') return 0;
        // 先按码点定位，再换算成"第几个字"，与 charAt 的口径保持一致
        const raw = chars.join('').indexOf(sub);
        if (raw < 0) return 0;
        return Array.from(chars.join('').slice(0, raw)).length + 1;
    }

    contains (args) {
        const text = Scratch.Cast.toString(args.TEXT);
        const sub = Scratch.Cast.toString(args.SUB);
        if (sub === '') return true;
        return text.indexOf(sub) >= 0;
    }

    changeCase (args) {
        const text = Scratch.Cast.toString(args.TEXT);
        return args.CASE === 'lower' ? text.toLowerCase() : text.toUpperCase();
    }

    trim (args) {
        return Scratch.Cast.toString(args.TEXT).trim();
    }

    splitPart (args) {
        const parts = this._parts(args.TEXT, args.SEP);
        const index = Math.round(Scratch.Cast.toNumber(args.INDEX));
        if (index < 1 || index > parts.length) return '';
        return parts[index - 1];
    }

    partCount (args) {
        return this._parts(args.TEXT, args.SEP).length;
    }

    _parts (text, sep) {
        const value = Scratch.Cast.toString(text);
        const separator = Scratch.Cast.toString(sep);
        if (value === '') return [];
        // 分隔符为空时按"每个字一段"处理，比返回整串更符合直觉
        if (separator === '') return Array.from(value);
        return value.split(separator);
    }
}

Scratch.extensions.register(new WpmStringV1());
