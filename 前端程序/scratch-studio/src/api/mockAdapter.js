/**
 * Mock adapter：在 STUDIO_USE_MOCK=1 时替代真实后端。
 * 响应形状与 client.js / types.js 完全一致，用于无后端联调的独立验证。
 * mock 模式下初始项目为空（has_starter=false），Studio 展示官方默认项目。
 */

const delay = (ms = 200) => new Promise(resolve => setTimeout(resolve, ms));

const mockChallenge = {
    block: {id: 1, lesson_id: 1, title: '闯关：绿旗动一动', required: true, completed: false},
    challenge: {
        id: 1,
        title: '绿旗动一动',
        instructions_md: '# 任务\n\n1. 从「事件」分类拖出绿旗积木\n2. 让角色移动 10 步\n3. 让角色说「你好」',
        version: 1,
        allowed_extensions: [],
        hints: ['先从「事件」分类里拖出绿旗积木'],
        checklist: ['绿旗被点击后让角色移动', '移动 10 步', '让角色说「你好」'],
        has_starter: false,
        starter_url: null
    },
    // 与真实 GET /lesson-blocks/{id} 对齐：后端会为当前学生和课时块创建
    // 一个尚无版本的作品壳。这样首次保存无需另一套“创建项目”接口。
    project: {
        id: 1,
        current_revision_no: 0,
        revision_count: 0,
        updated_at: null,
        content_url: null,
        revision: null
    },
    last_submission: null,
    // 与真实详情接口同构。mock 里挑战带示范项目，但未提交前 available=false、url=null——
    // 这正是要在无后端时验的那条分支：入口按钮不该在提交前出现。
    demo: {
        has_demo: true,
        available: false,
        url: null,
        notice: '提交作品并得到结果后可查看教师示范项目。'
    },
    limits: {max_bytes: 10485760, save_rate_max: 30, save_rate_seconds: 60}
};

let mockRevisionNo = 0;
let mockAttemptNo = 0;
const mockSubmissions = [];

export function fetchLessonBlockContext (blockId) {
    // `&mock_demo=1` 直接把示范项目当成已开放，用来单看只读页的样子——否则要先在
    // mock 里保存并提交一次才走得到那一支（与 `mock_published=1` 同一套用法）。
    if (new URLSearchParams(window.location.search).get('mock_demo') === '1') {
        mockChallenge.demo.available = true;
        mockChallenge.demo.url = `/api/scratch/lesson-blocks/${blockId}/demo.sb3`;
        mockChallenge.demo.notice = null;
    }
    return delay().then(() => JSON.parse(JSON.stringify(mockChallenge)));
}

export function saveProjectSb3 (projectId, sb3Blob, source, challengeId) {
    if (projectId !== mockChallenge.project.id || challengeId !== mockChallenge.challenge.id) {
        return Promise.reject(new Error('作品与当前挑战不匹配，请刷新后重试'));
    }
    mockRevisionNo += 1;
    const revision = {
            revision_id: 100 + mockRevisionNo,
            revision_no: mockRevisionNo,
            size_bytes: sb3Blob ? sb3Blob.size : 0,
            sprite_count: 1,
            extensions: [],
            saved_at: new Date().toISOString()
    };
    mockChallenge.project.current_revision_no = mockRevisionNo;
    mockChallenge.project.revision_count = mockRevisionNo;
    mockChallenge.project.updated_at = revision.saved_at;
    mockChallenge.project.revision = revision;
    mockChallenge.project.content_url = `/api/scratch/projects/${projectId}/content.sb3`;
    return delay().then(() => ({project_id: projectId, unchanged: false, revision}));
}

export function submitProject (blockId) {
    if (mockRevisionNo === 0) {
        return Promise.reject(new Error('请先保存作品再提交'));
    }
    mockAttemptNo += 1;
    const submission = {
        submission_id: 4,
        attempt_no: mockAttemptNo,
        submission_status: 'needs_review',
        passed: false,
        score: null,
        revision_no: mockRevisionNo,
        feedback: {
            note: '（mock）已提交，等待服务端判定。',
            items: []
        },
        needs_review: true,
        completed: false,
        progress: {total: 2, done: 0, percent: 0},
        unlocked_block_ids: [],
        submitted_at: new Date().toISOString()
    };
    mockSubmissions.unshift({
        submission_id: submission.submission_id,
        attempt_no: submission.attempt_no,
        status: submission.submission_status,
        score: submission.score,
        submitted_at: submission.submitted_at
    });
    mockChallenge.last_submission = submission;
    // 提交拿到结果 → 示范项目开放。真实后端在详情接口里算这一步，mock 里手动跟上，
    // 否则无后端联调时永远走不到"只读查看"那条路。
    mockChallenge.demo.available = true;
    mockChallenge.demo.url = `/api/scratch/lesson-blocks/${blockId}/demo.sb3`;
    mockChallenge.demo.notice = null;
    return delay(400).then(() => ({...submission}));
}

export function fetchSubmissions () {
    return delay().then(() => ({submissions: JSON.parse(JSON.stringify(mockSubmissions))}));
}

export function fetchStarterSb3 () {
    return Promise.reject(new Error('mock 模式无初始项目（has_starter=false）'));
}

export function fetchDemoSb3 () {
    // mock 不造 .sb3 字节：只读模式的可测部分是"入口何时出现、顶栏长什么样"，
    // 装载失败正好能顺带验一次错误页文案。
    return Promise.reject(new Error('mock 模式无示范项目文件'));
}

export function fetchProjectContentSb3 () {
    return Promise.reject(new Error('mock 模式无项目版本'));
}

// ---- 管理端预览 / 编写初始项目 ----
//
// 默认给草稿态：教研要试的正是"能不能写回去"这条路。想验证发布后按钮变灰的样子，
// 在 URL 上加 `&mock_published=1`。

const mockAuthoringChallenge = {
    id: 1,
    title: '绿旗动一动',
    instructions_md: mockChallenge.challenge.instructions_md,
    version: 1,
    allowed_extensions: [],
    hints: mockChallenge.challenge.hints,
    checklist: mockChallenge.challenge.checklist,
    has_starter: false,
    starter_url: null
};

// 示范项目的状态与 starter 分开存：真实后端里它们是两列，mock 合成一个就验不出
// "点了示范项目的保存却写进了初始项目"这类事故。
const mockAuthoringDemo = {has_demo: false, demo_url: null};

export function fetchAdminStudioContext (challengeId) {
    const published = new URLSearchParams(window.location.search).get('mock_published') === '1';
    const id = Number(challengeId) || mockAuthoringChallenge.id;
    return delay().then(() => ({
        mode: 'admin_preview',
        readonly: true,
        block: null,
        challenge: {...mockAuthoringChallenge, id, status: published ? 'published' : 'draft'},
        project: null,
        last_submission: null,
        analysis: {available: false, notice: null},
        authoring: {
            can_write_starter: !published,
            can_write_demo: !published,
            starter_write_url: published
                ? null
                : `/api/admin/scratch/challenges/${id}/starter-project`,
            demo_write_url: published ? null : `/api/admin/scratch/challenges/${id}/demo-project`,
            has_demo: mockAuthoringDemo.has_demo,
            demo_url: mockAuthoringDemo.demo_url,
            locked_reason: published
                ? '已发布的挑战不能直接改，请先撤回为草稿或复制为新版本。'
                : null
        },
        limits: {...mockChallenge.limits}
    }));
}

export function fetchChallengeSb3 () {
    return Promise.reject(new Error('mock 模式无初始项目（has_starter=false）'));
}

export function fetchAdminReviewContext (submissionId) {
    const id = Number(submissionId) || 1;
    return delay().then(() => ({
        mode: 'admin_review',
        readonly: true,
        id,
        student_id: 101,
        student_name: '张小明（mock）',
        challenge_id: 1,
        challenge_title: '第一课：小猫打招呼（mock）',
        snapshot: {revision_no: 5, saved_at: null, content_hash: 'sha256:mock', size_bytes: 0, download_url: null}
    }));
}

export function fetchSubmissionSb3 () {
    return Promise.reject(new Error('mock 模式无提交快照'));
}

export function uploadChallengeProject (url, sb3Blob) {
    if (!url) return Promise.reject(new Error('当前状态不允许写回该项目'));
    // 按 URL 判断写的是哪一份，而不是信调用方传来的意图：真实后端就是靠路径分流的，
    // mock 跟着同一个判据，才能验出前端把两个 write_url 接错的情况。
    const isDemo = String(url).includes('demo-project');
    if (isDemo) {
        mockAuthoringDemo.has_demo = true;
        mockAuthoringDemo.demo_url = `${String(url).replace('/demo-project', '/demo.sb3')}`;
        return delay(400).then(() => ({
            has_demo: true,
            demo_url: mockAuthoringDemo.demo_url
        }));
    }
    mockAuthoringChallenge.has_starter = true;
    return delay(400).then(() => ({
        has_starter: true,
        starter_size_bytes: sb3Blob ? sb3Blob.size : 0,
        starter_sha256: `mock${Date.now()}`
    }));
}

// ---- 自由作品与作品广场（与 client.js 同形状，2026-08-14） ----

let mockWorkSeq = 1;
const mockWorks = new Map();

function mockWork (id, title, overrides = {}) {
    return {
        id,
        title,
        description: '',
        source: 'free',
        source_challenge_id: null,
        is_public: true,
        sprite_count: 0,
        size_bytes: 0,
        views: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        has_content: false,
        content_url: null,
        ...overrides
    };
}

export function createWork (title, isPublic = false) {
    const id = mockWorkSeq++;
    const work = mockWork(id, title || '未命名作品', {is_public: isPublic});
    mockWorks.set(id, work);
    return delay().then(() => ({...work, limits: {...mockChallenge.limits}}));
}

export function fetchMyWorks () {
    return delay().then(() => ({
        items: [...mockWorks.values()].map(w => ({...w}))
    }));
}

export function fetchWorkContext (workId) {
    const work = mockWorks.get(Number(workId));
    if (!work) return Promise.reject(new Error('作品不存在。'));
    return delay().then(() => ({...work, limits: {...mockChallenge.limits}}));
}

export function saveWorkSb3 (workId, sb3Blob, source) {
    const work = mockWorks.get(Number(workId));
    if (!work) return Promise.reject(new Error('作品不存在。'));
    work.has_content = true;
    work.sprite_count = 1;
    work.size_bytes = sb3Blob ? sb3Blob.size : 0;
    work.updated_at = new Date().toISOString();
    work.content_url = `/api/scratch/works/${work.id}/content.sb3`;
    return delay(400).then(() => ({work_id: work.id, unchanged: false, saved_at: work.updated_at}));
}

export function fetchWorkContentSb3 () {
    return Promise.reject(new Error('mock 模式无作品内容字节'));
}

export function updateWork (workId, patch) {
    const work = mockWorks.get(Number(workId));
    if (!work) return Promise.reject(new Error('作品不存在。'));
    if (patch.title != null) work.title = patch.title;
    if (patch.description != null) work.description = patch.description;
    if (patch.is_public != null) work.is_public = patch.is_public;
    work.updated_at = new Date().toISOString();
    return delay().then(() => ({...work}));
}

export function deleteWork (workId) {
    const ok = mockWorks.delete(Number(workId));
    if (!ok) return Promise.reject(new Error('作品不存在。'));
    return delay().then(() => null);
}

export function shareWork (projectId) {
    // mock：从闯关项目造一份自由作品快照。
    const id = mockWorkSeq++;
    const work = mockWork(id, mockChallenge.challenge.title, {
        source: 'challenge',
        source_challenge_id: mockChallenge.challenge.id,
        sprite_count: mockChallenge.project.revision ? mockChallenge.project.revision.sprite_count : 0,
        has_content: mockRevisionNo > 0,
        content_url: `/api/scratch/works/${id}/content.sb3`
    });
    mockWorks.set(id, work);
    return delay(400).then(() => ({...work, already_shared: false}));
}

export function fetchGallery (params = {}) {
    const keyword = String(params.keyword || '').trim();
    let items = [...mockWorks.values()].filter(w => w.is_public);
    if (keyword) {
        items = items.filter(w => w.title.includes(keyword));
    }
    if (params.sort === 'popular') {
        items.sort((a, b) => b.views - a.views);
    } else {
        items.sort((a, b) => b.created_at.localeCompare(a.created_at));
    }
    const page = Number(params.page) || 1;
    const size = Number(params.size) || 20;
    const slice = items.slice((page - 1) * size, page * size).map(w => ({
        ...w,
        author: {id: 101, username: '张小明'}
    }));
    return delay().then(() => ({total: items.length, page, page_size: size, items: slice}));
}

export function fetchGalleryWork (workId) {
    const work = mockWorks.get(Number(workId));
    if (!work || !work.is_public) return Promise.reject(new Error('该作品未公开或不存在。'));
    work.views += 1;
    return delay().then(() => ({
        ...work,
        author: {id: 101, username: '张小明'},
        mine: true
    }));
}

export function fetchGalleryContentSb3 () {
    return Promise.reject(new Error('mock 模式无作品内容字节'));
}
