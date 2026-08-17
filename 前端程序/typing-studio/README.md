# typing-studio · 字母乐园（3-6 岁）

学生端工具箱的**低龄入口**：3-6 岁字母乐园（字母收集模式），另有拼音练习。
7-12 / 13+ 的完整单词打字（词库/默写/错题本/数据统计/中文打字）在
**typing-studio-qwerty**（fork 自 qwerty-learner 的魔改版），工具箱两张卡分流：

- 字母乐园（3-6 岁）→ `/typing-studio/?age=3-6&mode=home`
- 打字星球（7 岁+）→ `/typing-studio-qwerty/`

## 接入方式

与 scratch-studio 同构：独立构建，产物部署到 `/typing-studio/`，主应用 `study-blog-vue`
通过新窗口打开：

```js
window.open("/typing-studio/?age=3-6&mode=letter", "_blank");
```

## URL 参数

| 参数 | 取值 | 说明 |
|---|---|---|
| `age` | `3-6` / `7-12` / `13+` | 年龄段 |
| `mode` | `home` / `letter` / `pinyin` / `dict` / `practice` / `chinese` | 游戏模式 |

（本应用保留 7-12/13+ 的 dict/practice/chinese 模式作为备选；主推低龄入口。）

## 本地开发

```bash
npm install
npm run dev       # http://127.0.0.1:8603（/api 代理到 127.0.0.1:8000 FastAPI）
npm run build     # 产物 dist/
npm run preview   # 本地预览构建产物
```

## 技术要点

- 打字引擎 `src/engine/typingEngine.js`：字符级对比 + 错误标记 + WPM/准确率/连击，
  strict（错必退格）/ flow（错标红继续）双策略。
- 发音：Web Speech API（零后端，离线可用）；音效：Web Audio 合成。
- 词库（src/data/）：Dolch（公共领域）、Fry（公共领域）、拼音常用字表；
  qwerty-learner 词库 JSON 在 public/dicts/ 按需加载。
- 成绩：localStorage（`typing-studio-progress`），二期上报后端。
