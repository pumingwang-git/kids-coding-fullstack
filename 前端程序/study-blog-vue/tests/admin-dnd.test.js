// @vitest-environment jsdom
// admin-dnd.js 拖拽排序器的 DOM 护栏测试。
//
// jsdom 没有原生 HTML5 DnD，这里手动派发 drag 事件并 mock dataTransfer/clientY：
//   clientY < 0  → 目标项中线以上（drop-before）
//   clientY > 0  → 目标项中线以下（drop-after）
// jsdom 的 getBoundingClientRect 全为 0，所以用 ±1 控制插前/插后。
// 覆盖：同容器排序 / 拖到自身 no-op / 跨空章节 / 失败回滚 / 保存期间禁止并发。
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createSortable, destroyAll } from "../public/admin/admin-dnd.js";

const tick = () => new Promise((r) => setTimeout(r, 0));

function mountLists() {
  document.body.innerHTML = `
    <ol id="listA" data-test="A"></ol>
    <ol id="listB" data-test="B"></ol>`;
  const listA = document.getElementById("listA");
  const listB = document.getElementById("listB");
  const fill = (el, ids) => {
    el.innerHTML = ids
      .map((id) => `<li class="dnd-item" data-id="${id}"><span class="drag-grip">⠿</span>${id}</li>`)
      .join("");
  };
  fill(listA, [1, 2, 3]);
  fill(listB, []);
  return { listA, listB };
}

const ids = (el) => [...el.querySelectorAll(".dnd-item")].map((n) => n.dataset.id);

function dragEvent(type, over, clientY = 0) {
  const ev = new Event(type, { bubbles: true, cancelable: true });
  if (type === "dragover" || type === "drop") {
    Object.defineProperty(ev, "clientY", { value: clientY });
  }
  if (type === "dragstart") {
    Object.defineProperty(ev, "dataTransfer", {
      value: { effectAllowed: "", dropEffect: "", setData: vi.fn() },
    });
  }
  over.dispatchEvent(ev);
  return ev;
}

/** 模拟一次完整拖拽：按住手柄 → dragstart → dragover → drop → dragend。 */
async function drag(fromItem, overItem, clientY = 0) {
  const grip = fromItem.querySelector(".drag-grip");
  dragEvent("mousedown", grip);
  dragEvent("dragstart", fromItem);
  dragEvent("dragover", overItem, clientY);
  dragEvent("drop", overItem, clientY);
  dragEvent("dragend", fromItem);
  await tick();
}

const instances = [];
function install(listEl, onReorder, extra = {}) {
  const inst = createSortable(listEl, {
    items: ".dnd-item",
    grip: ".drag-grip",
    group: "g",
    parentId: listEl.dataset.test,
    onReorder,
    ...extra,
  });
  instances.push(inst);
  return inst;
}

beforeEach(() => {
  instances.length = 0;
});

afterEach(() => {
  destroyAll(instances);
  document.body.innerHTML = "";
});

describe("同容器排序", () => {
  it("把第 1 项拖到第 3 项之后 → 顺序 2,3,1 且回调带正确 orderedIds", async () => {
    const { listA } = mountLists();
    const onReorder = vi.fn().mockResolvedValue(undefined);
    install(listA, onReorder);

    const [first] = listA.querySelectorAll(".dnd-item");
    const third = listA.querySelectorAll(".dnd-item")[2];
    await drag(first, third, 1); // after

    expect(ids(listA)).toEqual(["2", "3", "1"]);
    expect(onReorder).toHaveBeenCalledTimes(1);
    expect(onReorder.mock.calls[0][0].orderedIds).toEqual(["2", "3", "1"]);
    expect(onReorder.mock.calls[0][0].crossContainer).toBe(false);
  });
});

describe("拖到自身", () => {
  it("目标就是被拖项 → no-op：不发请求、DOM 顺序不变", async () => {
    const { listA } = mountLists();
    const onReorder = vi.fn().mockResolvedValue(undefined);
    install(listA, onReorder);

    const [first] = listA.querySelectorAll(".dnd-item");
    await drag(first, first, 0);

    expect(ids(listA)).toEqual(["1", "2", "3"]);
    expect(onReorder).not.toHaveBeenCalled();
  });

  it("拖回原位（相邻落点）→ 顺序未变也不发请求", async () => {
    const { listA } = mountLists();
    const onReorder = vi.fn().mockResolvedValue(undefined);
    install(listA, onReorder);

    const items = listA.querySelectorAll(".dnd-item");
    await drag(items[1], items[0], 1); // 2 拖到 1 之后 = 原位

    expect(ids(listA)).toEqual(["1", "2", "3"]);
    expect(onReorder).not.toHaveBeenCalled();
  });
});

describe("跨空章节", () => {
  it("课时拖入空章节 → 进目标容器末尾，带 from/to parentId 与 sourceOrderedIds", async () => {
    const { listA, listB } = mountLists();
    const onReorder = vi.fn().mockResolvedValue(undefined);
    install(listA, onReorder);
    install(listB, onReorder);

    const items = listA.querySelectorAll(".dnd-item");
    await drag(items[1], listB, 0); // 落点不是具体项 → appendChild

    expect(ids(listA)).toEqual(["1", "3"]);
    expect(ids(listB)).toEqual(["2"]);
    expect(onReorder).toHaveBeenCalledTimes(1);
    const detail = onReorder.mock.calls[0][0];
    expect(detail.crossContainer).toBe(true);
    expect(detail.movedId).toBe("2");
    expect(detail.fromParentId).toBe("A");
    expect(detail.toParentId).toBe("B");
    expect(detail.orderedIds).toEqual(["2"]);
    expect(detail.sourceOrderedIds).toEqual(["1", "3"]);
  });
});

describe("失败回滚", () => {
  it("revert() 能把乐观移动的节点放回原位", async () => {
    const { listA } = mountLists();
    let captured;
    const onReorder = vi.fn().mockImplementation(async (detail) => {
      captured = detail;
    });
    install(listA, onReorder);

    const items = listA.querySelectorAll(".dnd-item");
    await drag(items[0], items[2], 1); // 1 拖到 3 之后
    expect(ids(listA)).toEqual(["2", "3", "1"]); // 乐观更新已生效

    // 模拟请求失败：调用方在 catch 里执行 revert
    captured.revert();
    expect(ids(listA)).toEqual(["1", "2", "3"]); // 还原
    expect(items[0].parentElement.id).toBe("listA");
  });
});

describe("保存期间禁止并发", () => {
  it("onReorder 在途时新的 dragstart 被拒绝", async () => {
    const { listA } = mountLists();
    let release;
    const gate = new Promise((r) => (release = r));
    const onReorder = vi.fn().mockReturnValue(gate);
    install(listA, onReorder);

    const items = listA.querySelectorAll(".dnd-item");
    // 第一次拖拽：请求挂起（busy=true）
    await drag(items[0], items[2], 1);
    expect(onReorder).toHaveBeenCalledTimes(1);

    // 第二次拖拽：dragstart 被 busy 闸拒绝
    const grip2 = items[1].querySelector(".drag-grip");
    dragEvent("mousedown", grip2);
    const ev = dragEvent("dragstart", items[1]);
    expect(ev.defaultPrevented).toBe(true);

    release();
    await tick();
    expect(onReorder).toHaveBeenCalledTimes(1); // 第二次没有进入 onReorder
  });
});
