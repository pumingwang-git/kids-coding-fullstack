/**
 * Scratch 平台 API 契约类型 —— 唯一事实来源。
 * 与《21b、Claude-Scratch后端开发任务书》冻结接口对齐，禁止发明第二套接口。
 * 真实实现（client.js）与 mock（mockAdapter.js）共用本类型。
 */

// GET /api/scratch/lesson-blocks/{block_id}
export const LessonBlockContextShape = {
    block: null,
    challenge: null,
    project: null,
    last_submission: null,
    limits: null
};

// PUT /api/scratch/projects/{project_id}
export const SaveProjectResponseShape = {
    project_id: null,
    unchanged: null,
    revision: null
};

// POST /api/scratch/lesson-blocks/{block_id}/submit
export const SubmitResponseShape = {
    submission_id: null,
    attempt_no: null,
    submission_status: null, // 'passed' | 'failed' | 'needs_review'
    passed: null,
    score: null,
    revision_no: null,
    feedback: null,
    needs_review: null,
    completed: null,
    progress: null,           // {total, done, percent}
    unlocked_block_ids: null
};

// 状态词表（与后端一致；不含 mock 曾用的 evaluating/pending_review）
export const SUBMISSION_STATUS = ['passed', 'failed', 'needs_review'];

// 保存来源（PUT 的 source 字段）
export const SAVE_SOURCE = {
    AUTOSAVE: 'autosave',
    MANUAL: 'manual'
};
