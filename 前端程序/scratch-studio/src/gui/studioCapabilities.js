/**
 * 六种工作台形态各自开放哪些能力。
 *
 * 单独成表的原因：这张表原先是写在 JSX 里的一串布尔表达式，其中
 *
 *     canManageFiles={freeEdit || !(studentDemo || galleryPreview || adminReview)}
 *
 * 的注释写着"闯关（防下载答案）一律关掉"，但真算出来闯关是 **true** ——
 * `false || !(false)` = true。也就是说学生做作业时「文件」菜单一直开着，
 * 「保存到你的电脑」能把作业下载走、「从电脑上传」能把同学的 .sb3 传上来交。
 * 一串就地拼的布尔表达式没人能一眼验对，所以把它抽成一张能被测试钉住的表。
 *
 * 新增形态时**必须**同时在 `tests/scratch-studio-capabilities.test.js` 里补一行，
 * 那边有一条"每种形态都要在表里"的哨兵。
 */

/** 六种形态。与 StudioApp 的 URL 参数一一对应。 */
export const STUDIO_MODES = Object.freeze([
    'free',            // ?mode=free            学生自由创作
    'challenge',       // ?block_id=N           课中挑战 / 课时作业（同一条路）
    'admin_preview',   // ?mode=admin_preview   教研录制初始项目 / 示范项目
    'admin_review',    // ?mode=admin_review    教师批改台看提交快照
    'student_demo',    // ?mode=student_demo    学生看教师示范项目
    'gallery_preview'  // ?mode=preview         看广场上别人的公开作品
]);

const TABLE = {
    free: {
        // 自己的创作，导入导出都随意。
        canManageFiles: true,
        canEditTitle: true,
        showDebug: true,
        tone: 'student'
    },
    challenge: {
        // 作业与课中挑战走同一条路。**关掉文件菜单**：
        //  - 「保存到你的电脑」= 一键把作业导出，同学之间可以互传；
        //  - 「从电脑上传」   = 拿别人的 .sb3 顶替自己的作业交上去；
        //  - 「新建」        = 一点清空自己写了半天的东西。
        // 这是移除入口，不是防篡改——真正的判定边界在后端的提交闸。
        canManageFiles: false,
        // 作业名是老师定的，学生不该改。
        canEditTitle: false,
        // Debug 是 Scratch 的通用排障向导，不属于学生作业流程；教程保留。
        showDebug: false,
        tone: 'student'
    },
    admin_preview: {
        // 教研要能把手头现成的 .sb3 传进来当初始项目，这条是他们的正经工作方式。
        canManageFiles: true,
        // 关卡标题在管理端改，不在工作台改。
        canEditTitle: false,
        showDebug: true,
        tone: 'admin'
    },
    admin_review: {
        // 只读看学生交上来的快照，一个写入口都不给。
        canManageFiles: false,
        canEditTitle: false,
        showDebug: true,
        tone: 'admin'
    },
    student_demo: {
        // 看老师示范：给了文件菜单就等于给了「把答案下载走」。
        canManageFiles: false,
        canEditTitle: false,
        showDebug: true,
        tone: 'readonly'
    },
    gallery_preview: {
        // 看别人的公开作品：同上，且改动本来就不会保存。
        canManageFiles: false,
        canEditTitle: false,
        showDebug: true,
        tone: 'readonly'
    }
};

/**
 * 取某种形态的能力表。未知形态按**最保守**的一档处理（什么都不开）：
 * 拼错参数应该少给能力，而不是多给。
 */
export function capabilitiesFor (mode) {
    return TABLE[mode] || {
        canManageFiles: false,
        canEditTitle: false,
        showDebug: false,
        tone: 'readonly'
    };
}

export default capabilitiesFor;
