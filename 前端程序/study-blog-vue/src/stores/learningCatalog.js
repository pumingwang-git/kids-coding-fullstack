import { reactive } from "vue";
import { request } from "../services/auth";

export const learningCatalog = reactive({ areas: [], loaded: false, loading: null });

export async function ensureLearningAreas(force = false) {
  if (learningCatalog.loaded && !force) return learningCatalog.areas;
  if (!learningCatalog.loading) {
    learningCatalog.loading = request("/api/learning-areas")
      .then((data) => {
        learningCatalog.areas = data.items || [];
        learningCatalog.loaded = true;
        return learningCatalog.areas;
      })
      .finally(() => {
        learningCatalog.loading = null;
      });
  }
  return learningCatalog.loading;
}

export function areaByKey(key) {
  return learningCatalog.areas.find((item) => item.key === key) || null;
}

export function modulePath(areaKey, moduleKey) {
  if (moduleKey === "overview") return `/areas/${areaKey}`;
  if (moduleKey === "question-bank") return `/areas/${areaKey}/tasks/mistakes`;
  return `/areas/${areaKey}/${moduleKey}`;
}
