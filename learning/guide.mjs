// Pure, data-driven teaching-guide helpers. Edit data/learning-guide.json, not this code.
const SLUG = /^[a-z0-9][a-z0-9-]*$/;
const readable = value => typeof value === "string" && value.trim().length > 0;
const publicUrl = value => {
  if (!readable(value)) return false;
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password;
  } catch { return false; }
};
export const referenceSelectionId = id => "ref-" + id;

export function validateExpertGuide(index, validReferenceIds) {
  if (!index || index.schema !== "sparkles-learning-guide/1" ||
      !Array.isArray(index.lessons) || !index.lessons.length)
    throw new Error("Unsupported learning guide format");
  const seen = new Set();
  for (const lesson of index.lessons) {
    if (!lesson || !SLUG.test(lesson.id) || seen.has(lesson.id) ||
        ![lesson.category, lesson.title, lesson.summary, lesson.prompt].every(readable) ||
        !publicUrl(lesson.source_url) || !Array.isArray(lesson.examples) || !lesson.examples.length)
      throw new Error("Invalid or duplicate learning guide category");
    seen.add(lesson.id);
    const exampleIds = new Set();
    for (const example of lesson.examples) {
      if (!example || !SLUG.test(example.id) || exampleIds.has(example.id) ||
          !validReferenceIds.has(referenceSelectionId(example.id)) ||
          !readable(example.label) || !readable(example.comment))
        throw new Error("Learning guide has an invalid or missing reference: " + example?.id);
      exampleIds.add(example.id);
    }
    if (lesson.featured_pair !== undefined && (
        !Array.isArray(lesson.featured_pair) || lesson.featured_pair.length !== 2 ||
        lesson.featured_pair[0] === lesson.featured_pair[1] ||
        !lesson.featured_pair.every(id => exampleIds.has(id))))
      throw new Error("Invalid featured comparison pair in " + lesson.id);
    if (lesson.annotated_source !== undefined &&
        (!readable(lesson.annotated_source?.label) ||
         !publicUrl(lesson.annotated_source?.url)))
      throw new Error("Invalid annotated original source in " + lesson.id);
  }
  return index.lessons;
}

// Compare all teaching examples in editorial order. Never silently truncate.
export function comparisonExamples(lesson, validIds, maxSelection=10) {
  if (!lesson || !Array.isArray(lesson.examples) ||
      lesson.examples.length < 2 || lesson.examples.length > maxSelection) return [];
  const ids=lesson.examples.map(example=>referenceSelectionId(example.id));
  return new Set(ids).size===ids.length && ids.every(id=>validIds.has(id)) ? ids : [];
}
