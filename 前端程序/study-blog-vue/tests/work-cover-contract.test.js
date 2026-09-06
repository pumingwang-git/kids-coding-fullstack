// 作品封面的前后端契约（设计见《63、Scratch 作品封面》）。
//
// 服务端保证 `thumbnail_url` **永不为空**：存了舞台截图就发截图，没存（老作品、
// 闯关分享来的快照、截图失败、封面文件丢了）就发一张生成的占位图。这条保证换来
// 前端的两条纪律，这里各守一条：
//
//  1. **不自己拼封面路径。** 地址上带内容哈希做缓存版本号（`?v=<sha 前 12 位>`），
//     前端拼不出来；拼了就等于把「封面换了地址跟着变」这条机制绕过去，学生会一直
//     看到缓存里的旧图。
//  2. **不写空值兜底。** 曾经三个页面各有一段 `v-else` 的占位 SVG，因为
//     `thumbnail_url` 永不为空，那段是走不到的死代码——已删。再加回来只会掩盖
//     「服务端真的没给地址」这类问题。
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const VIEWS = ["MyWorks", "CreateHub", "ExploreHome"];

function source(name) {
  return readFileSync(
    fileURLToPath(new URL(`../src/views/${name}.vue`, import.meta.url)),
    "utf8",
  );
}

describe("作品封面契约", () => {
  it.each(VIEWS)("%s 只读 thumbnail_url，不自己拼封面路径", (name) => {
    const text = source(name);
    expect(text).toContain(':src="work.thumbnail_url"');
    expect(text).not.toMatch(/\/api\/scratch\/(works|gallery)\/[^"']*cover/);
  });

  it.each(VIEWS)("%s 不再有走不到的占位分支", (name) => {
    expect(source(name)).not.toContain("work-cover-placeholder");
  });
});
