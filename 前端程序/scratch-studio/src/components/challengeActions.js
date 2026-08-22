/**
 * 作业顶栏的状态策略。
 *
 * 这组纯函数把“提交按钮该说什么、能不能看示范项目”从 React 渲染中抽出来，
 * 让作业规则能被跨包 Vitest 直接覆盖。
 */
export const SUBMISSION_STATUS_TEXT = Object.freeze({
    passed: '已通过',
    failed: '未通过',
    needs_review: '待人工点评',
    returned: '已退回重做'
});

export function submitActionFor (lastSubmission, hasSavedRevision, isSubmitting) {
    const passed = lastSubmission && lastSubmission.submission_status === 'passed';
    return {
        label: isSubmitting ? (passed ? '重新提交中…' : '提交中…') : (passed ? '再提交' : '提交作品'),
        primary: !passed,
        disabled: Boolean(isSubmitting || !hasSavedRevision),
        title: hasSavedRevision ? '' : '请先保存作品'
    };
}

export function canViewTeacherDemo (demo, href) {
    return Boolean(demo && demo.available && href);
}
