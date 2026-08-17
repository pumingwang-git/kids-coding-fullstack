// 题干配图的"点开看大图"。
//
// 做成模块级单例而不是 MarkdownBody 内部状态：MarkdownBody 在一屏里能有十几个实例
// （题干、四个选项、须知、解析、编程题的输入输出格式各一个），每个都挂一层遮罩既浪费，
// 也会出现两层遮罩叠在一起的观感。挂载点只有一处，见 ExamView 模板里的 <ImageLightbox>。
import { reactive } from "vue";

export const lightbox = reactive({
  src: "", // 空串 = 关闭。不另设 open 字段，免得两个字段对不上
  alt: "",
});

export function openLightbox(src, alt = "") {
  if (!src) return;
  lightbox.src = src;
  lightbox.alt = alt;
}

export function closeLightbox() {
  lightbox.src = "";
  lightbox.alt = "";
}
