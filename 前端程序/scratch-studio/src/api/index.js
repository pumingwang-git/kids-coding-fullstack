/**
 * API 门面：根据 STUDIO_USE_MOCK 切换真实 / mock 实现。
 * 调用方只 import 本文件，不关心底层实现。
 */

// 由 webpack.config.js 的 DefinePlugin 在构建期替换。浏览器中没有 Node `process`，
// 不能写成 process.env.STUDIO_USE_MOCK，否则页面会在加载 API 门面时直接白屏。
const USE_MOCK = __STUDIO_USE_MOCK__;

import * as real from './client';
import * as mock from './mockAdapter';

export const useMock = () => USE_MOCK;

const impl = USE_MOCK ? mock : real;

export const fetchLessonBlockContext = impl.fetchLessonBlockContext;
export const fetchStarterSb3 = impl.fetchStarterSb3;
export const fetchDemoSb3 = impl.fetchDemoSb3;
export const fetchProjectContentSb3 = impl.fetchProjectContentSb3;
export const saveProjectSb3 = impl.saveProjectSb3;
export const submitProject = impl.submitProject;
export const fetchSubmissions = impl.fetchSubmissions;
export const fetchAdminStudioContext = impl.fetchAdminStudioContext;
export const fetchChallengeSb3 = impl.fetchChallengeSb3;
export const uploadChallengeProject = impl.uploadChallengeProject;
export const fetchAdminReviewContext = impl.fetchAdminReviewContext;
export const fetchSubmissionSb3 = impl.fetchSubmissionSb3;
export const createWork = impl.createWork;
export const fetchMyWorks = impl.fetchMyWorks;
export const fetchWorkContext = impl.fetchWorkContext;
export const saveWorkSb3 = impl.saveWorkSb3;
export const fetchWorkContentSb3 = impl.fetchWorkContentSb3;
export const updateWork = impl.updateWork;
export const deleteWork = impl.deleteWork;
export const shareWork = impl.shareWork;
export const fetchGallery = impl.fetchGallery;
export const fetchGalleryWork = impl.fetchGalleryWork;
export const fetchGalleryContentSb3 = impl.fetchGalleryContentSb3;
export {getCookie} from './client';
