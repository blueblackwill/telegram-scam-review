/* Match only the synthetic evidence rows displayed by the local walkthrough. */
window.detectTrainingEvidence = function detectTrainingEvidence(rows, spec) {
  const findings = new Map();
  const patterns = spec.rules.map((rule) => ({
    rule,
    english: rule.english === null ? null : new RegExp(rule.english),
  }));
  const domain = new RegExp(spec.domainPattern);

  function add({ rule, category, title, summary, status, grade }, row) {
    if (!findings.has(rule)) {
      findings.set(rule, { rule, category, title, summary, status, grade, row, method: "detector" });
    }
  }

  rows.forEach(({ text }, row) => {
    const spaced = text.normalize("NFKC").toLowerCase().replace(/\p{Cf}/gu, "")
      .replace(/\s+/gu, " ").trim();
    const compact = spaced.replace(/\s/gu, "");

    for (const { rule, english } of patterns) {
      const exact = rule.exact.includes(compact);
      const rejected = rule.rejectPrefixes.some((prefix) => compact.startsWith(prefix));
      const matches = (english !== null && english.test(spaced)) ||
        rule.chinese.some((fragment) => compact.includes(fragment));
      if (exact || (!rejected && matches)) add(rule, row);
    }

    if (domain.test(spaced)) add(spec.visibleAddress, row);
  });

  return [...findings.values()];
};
