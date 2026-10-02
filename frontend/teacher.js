import { api, ApiError, busy, currentUser, h, marks, toast, token, upload } from "./app.js";

const main = document.querySelector("#main");
const panel = document.querySelector("#panel");
const JUDGES = [["claude", "Claude"], ["openai", "GPT"], ["gemini", "Gemini"]];
let exam = null;
let results = null;
let events = null;
let live = {};
const plural = (n, one, many) => (Number(n) === 1 ? one : many);
const statusWord = (status) => ({ queued: "Queued", reading: "Reading", grading: "Grading", failed: "Failed" })[status] ?? "–";

await currentUser();
document.querySelector("#new-exam").addEventListener("click", newExam);
window.addEventListener("hashchange", route);
document.addEventListener("keydown", (event) => event.key === "Escape" && closePanel());
await loadExams();
await route();

function examId() {
  return Number(new URLSearchParams(location.hash.slice(1)).get("exam")) || null;
}

async function loadExams() {
  const exams = await api("/api/exams");
  const list = document.querySelector("#exam-list");
  list.replaceChildren(...exams.map((e) =>
    h("a", { href: `#exam=${e.exam_id}`, class: "exam-link", "aria-current": e.exam_id === examId() ? "page" : null },
      h("span", { class: "exam-title" }, e.title),
      h("span", { class: "exam-meta" }, e.status === "draft" ? "Setting up" : e.status === "released" ? "Released" : `${e.graded} of ${e.sheets} sheets graded`))));
  if (!exams.length) list.append(h("p", { class: "muted small", style: "padding: 0 12px" }, "Your exams will appear here."));
}

async function route() {
  closePanel();
  events?.close();
  events = null;
  document.querySelectorAll(".exam-link").forEach((a) => a.setAttribute("aria-current", a.hash === location.hash ? "page" : "false"));
  const id = examId();
  if (!id) return welcome();
  try {
    exam = await api(`/api/exams/${id}`);
    results = exam.status === "draft" ? null : await api(`/api/exams/${id}/results`);
    render();
    if (exam.status === "ready") listen(id);
  } catch (error) {
    main.replaceChildren(h("div", { class: "page" }, h("p", { class: "error" }, error.message)));
  }
}

async function reload() {
  exam = await api(`/api/exams/${exam.exam_id}`);
  results = exam.status === "draft" ? null : await api(`/api/exams/${exam.exam_id}/results`);
  render();
  await loadExams();
}

function welcome() {
  main.replaceChildren(h("div", { class: "page" }, h("div", { class: "welcome" },
    h("h1", {}, "Start with an exam"),
    h("p", { class: "muted" }, "Create an exam, upload its answer key, check the marking scheme, then drop in the scanned sheets. Grades fill in as each sheet is read."),
    h("div", {}, h("button", { class: "primary", onclick: newExam }, "New exam")))));
}

function newExam() {
  const title = h("input", { required: true, maxlength: 200, placeholder: "Data Structures Midterm 1" });
  main.replaceChildren(h("div", { class: "page" }, h("form", {
    class: "card section", style: "max-width: 520px",
    onsubmit: async (event) => {
      event.preventDefault();
      const created = await busy(event.submitter, "Creating…", () => api("/api/exams", { method: "POST", body: { title: title.value } }));
      location.hash = `exam=${created.exam_id}`;
      await loadExams();
    },
  }, h("h2", {}, "New exam"), h("label", {}, "Exam title", title), h("div", {}, h("button", { class: "primary", type: "submit" }, "Create exam")))));
  title.focus();
}

function render() {
  const ready = exam.status !== "draft";
  live = ready ? { sheets: sheetsSection(), grades: gradesSection() } : {};
  main.replaceChildren(h("div", { class: "page" },
    header(),
    ready ? setupSummary() : h("section", { class: "card" }, steps()),
    live.sheets,
    live.grades,
    exam.status === "released" ? regrades() : null,
    ready ? stats() : null));
}

function header() {
  const status = { draft: ["Setting up", "quiet"], ready: ["Grading", ""], released: ["Released to students", "good"] }[exam.status];
  return h("div", { class: "page-head" },
    h("div", { class: "title" }, h("h1", {}, exam.title), h("div", {}, h("span", { class: `pill ${status[1]}` }, status[0]))),
    exam.status === "draft" ? null : h("div", { class: "actions" },
      h("button", { onclick: exportCsv }, "Export CSV"),
      exam.status === "ready" ? h("button", { class: "primary", onclick: release }, "Release results") : null));
}

function fileStep({ title, description, accept, path, done, doneText, busyText }) {
  const input = h("input", { type: "file", accept, "aria-label": title });
  const button = h("button", {
    onclick: async () => {
      if (!input.files.length) return toast("Choose a file first.", "bad");
      const updated = await busy(button, busyText, () => api(`/api/exams/${exam.exam_id}/${path}`, { method: "POST", form: upload(input.files[0]) }));
      if (updated.skipped?.length) toast(`Skipped ${updated.skipped.length} emails that belong to staff accounts.`);
      await reload();
    },
  }, done ? "Replace" : "Upload");
  return h("li", { class: `step${done ? " done" : ""}` }, h("div", { class: "step-body" },
    h("h3", {}, title), h("p", {}, done ? doneText : description), h("div", { class: "upload-row" }, input, button)));
}

function steps() {
  const hasKey = exam.questions.length > 0;
  return h("ol", { class: "steps" },
    fileStep({
      title: "Answer key", path: "key", accept: ".pdf,.png,.jpg,.jpeg,.txt", done: hasKey, busyText: "Reading the key…",
      description: "Upload the key as a PDF, photo or text file, with the marks written next to each question. Reading it takes up to a minute.",
      doneText: `Read ${exam.questions.length}${plural(exam.questions.length, " question", " questions")}. Uploading again replaces them.`,
    }),
    h("li", { class: "step" }, h("div", { class: "step-body" },
      h("h3", {}, "Marking scheme"),
      hasKey ? schemeEditor() : h("p", {}, "Each reference answer is split into rubric points once the key is read. You check them here before any grading starts."))),
    fileStep({
      title: "Teacher notes (optional)", path: "notes", accept: ".pdf,.txt", done: exam.notes_chunks > 0, busyText: "Storing notes…",
      description: "Lecture notes or textbook sections the judges should grade against when the key doesn't spell something out.",
      doneText: `${exam.notes_chunks}${plural(exam.notes_chunks, " section", " sections")} stored. Upload more to add to them.`,
    }),
    fileStep({
      title: "Class roster", path: "roster", accept: ".csv", done: exam.roster_size > 0, busyText: "Inviting students…",
      description: "A CSV with student_id, name and email columns. Student IDs are matched against the ID box on each sheet, and students get an invite to see their results.",
      doneText: `${exam.roster_size}${plural(exam.roster_size, " student", " students")} on the roster.`,
    }));
}

function schemeEditor() {
  const draft = structuredClone(exam.questions).map((q) => ({ ...q, max_marks: Number(q.max_marks), points: q.points.map((p) => ({ description: p.description, marks: Number(p.marks) })) }));
  const list = h("div", { class: "scheme" });
  const problems = h("ul", { class: "problems", role: "alert" });
  const sums = new Map();

  const total = (q) => q.points.reduce((sum, p) => sum + (Number(p.marks) || 0), 0);
  const showSum = (q) => {
    const node = sums.get(q);
    const off = Math.abs(total(q) - q.max_marks) > 1e-9;
    node.className = off ? "sum off" : "sum";
    node.textContent = `Points add up to ${marks(total(q))} of ${marks(q.max_marks)}`;
  };
  const number = (value, onInput, label) => h("input", { type: "number", class: "num", min: 0, step: 0.5, value, "aria-label": label, oninput: (e) => onInput(Number(e.target.value)) });

  function draw() {
    list.replaceChildren(...draft.map((q) => {
      const sum = h("span");
      sums.set(q, sum);
      const block = h("fieldset", { class: "question" },
        h("legend", {}, `Question ${q.number}`),
        q.text ? h("p", { class: "question-text" }, q.text) : null,
        h("p", { class: "reference" }, q.reference_answer),
        h("label", { class: "inline" }, "Worth", number(q.max_marks, (v) => { q.max_marks = v; showSum(q); }, `Marks for question ${q.number}`), "marks"),
        h("div", { class: "points" }, q.points.map((p, i) => h("div", { class: "point-row" },
          h("input", { value: p.description, "aria-label": `Rubric point ${i + 1}`, oninput: (e) => { p.description = e.target.value; } }),
          number(p.marks, (v) => { p.marks = v; showSum(q); }, `Marks for rubric point ${i + 1}`),
          h("button", { class: "icon", type: "button", "aria-label": `Remove rubric point ${i + 1}`, onclick: () => { q.points.splice(i, 1); draw(); } }, "×")))),
        h("div", { class: "point-footer" },
          h("button", { class: "link", type: "button", onclick: () => { q.points.push({ description: "", marks: 1 }); draw(); } }, "Add point"),
          sum));
      showSum(q);
      return block;
    }));
  }
  draw();

  const save = () => api(`/api/exams/${exam.exam_id}/scheme`, {
    method: "PUT",
    body: { questions: draft.map((q) => ({ question_id: q.question_id, max_marks: q.max_marks, points: q.points.filter((p) => p.marks > 0) })) },
  });
  const saveButton = h("button", { onclick: async () => { await busy(saveButton, "Saving…", save); toast("Scheme saved"); } }, "Save changes");
  const confirmButton = h("button", {
    class: "primary",
    onclick: async () => {
      problems.replaceChildren();
      try {
        await busy(confirmButton, "Checking…", async () => { await save(); await api(`/api/exams/${exam.exam_id}/confirm`, { method: "POST" }); });
        toast("Scheme confirmed. You can upload sheets now.");
        await reload();
        listen(exam.exam_id);
      } catch (error) {
        if (error instanceof ApiError && error.detail?.problems) problems.replaceChildren(...error.detail.problems.map((p) => h("li", {}, p)));
      }
    },
  }, "Confirm scheme");
  return h("div", { class: "section" },
    h("p", {}, "Check that each question's points cover what a full answer needs and add up to its marks. Once confirmed, the scheme is fixed for every student."),
    list, problems, h("div", { class: "actions" }, saveButton, confirmButton));
}

function setupSummary() {
  const questionCount = exam.questions.length;
  const totalMarks = exam.questions.reduce((sum, q) => sum + Number(q.max_marks), 0);
  const addFile = (path, accept, label) => {
    const input = h("input", { type: "file", accept, class: "visually-hidden", onchange: async () => {
      await api(`/api/exams/${exam.exam_id}/${path}`, { method: "POST", form: upload(input.files[0]) }).catch((e) => toast(e.message, "bad"));
      await reload();
    } });
    return h("label", { class: "button" }, label, input);
  };
  return h("section", { class: "card section" },
    h("div", { class: "section-head" },
      h("h2", {}, "Setup"),
      h("p", { class: "muted small" }, `${questionCount}${plural(questionCount, " question", " questions")} worth ${marks(totalMarks)} marks, ${exam.notes_chunks}${plural(exam.notes_chunks, " note section", " note sections")}, ${exam.roster_size}${plural(exam.roster_size, " student", " students")}`)),
    exam.status === "ready" ? h("div", { class: "actions" }, addFile("roster", ".csv", "Add students"), addFile("notes", ".pdf,.txt", "Add notes")) : null);
}

function sheetsSection() {
  const s = results.summary;
  const share = s.sheets ? (100 * s.graded) / s.sheets : 0;
  const input = h("input", { type: "file", multiple: true, accept: "image/*,application/pdf", id: "sheet-input", class: "visually-hidden", onchange: (e) => sendSheets(e.target.files) });
  const zone = h("label", {
    for: "sheet-input", class: "dropzone",
    ondragover: (e) => { e.preventDefault(); zone.classList.add("over"); },
    ondragleave: () => zone.classList.remove("over"),
    ondrop: (e) => { e.preventDefault(); zone.classList.remove("over"); sendSheets(e.dataTransfer.files); },
  }, h("strong", {}, "Drop scanned answer sheets here"), h("span", { class: "muted small" }, "or choose files. PDFs and photos both work, one student per file."));
  return h("section", { class: "section" },
    h("div", { class: "section-head" }, h("h2", {}, "Answer sheets")),
    exam.status === "ready" ? [input, zone] : null,
    s.sheets ? [
      h("div", { class: "bar", role: "progressbar", "aria-valuenow": Math.round(share), "aria-valuemin": 0, "aria-valuemax": 100 }, h("span", { style: `width: ${share}%` })),
      h("div", { class: "progress" },
        h("span", {}, h("strong", {}, s.graded), ` of ${s.sheets} sheets graded`),
        h("span", {}, h("strong", {}, s.flagged), plural(s.flagged, " answer", " answers"), " flagged"),
        s.unmatched ? h("span", {}, h("strong", {}, s.unmatched), plural(s.unmatched, " sheet needs", " sheets need"), " a student") : null,
        s.failed ? h("span", { class: "error" }, h("strong", {}, s.failed), plural(s.failed, " answer", " answers"), " couldn't be graded") : null,
        s.average != null ? h("span", {}, "Class average ", h("strong", {}, marks(s.average))) : null),
    ] : null);
}

async function sendSheets(files) {
  if (!files.length) return;
  const form = new FormData();
  [...files].forEach((file) => form.append("files", file));
  try {
    const { queued } = await api(`/api/exams/${exam.exam_id}/sheets`, { method: "POST", form });
    toast(`${queued}${plural(queued, " sheet", " sheets")} queued for grading`);
    await refreshLive();
  } catch (error) {
    toast(error.message, "bad");
  }
}

function gradesSection() {
  if (!results.rows.length) return h("section", { class: "section" }, h("h2", {}, "Grades"), h("p", { class: "empty" }, "Grades appear here as each sheet is graded."));
  return h("section", { class: "section" },
    h("div", { class: "section-head" }, h("h2", {}, "Grades"), h("p", { class: "muted small" }, "Amber marks are flagged for a second look. Click any mark to see how it was given.")),
    h("div", { class: "table-wrap" }, h("table", {},
      h("thead", {}, h("tr", {},
        h("th", { scope: "col" }, "Student"),
        results.questions.map((q) => h("th", { scope: "col", class: "num" }, `Q${q.number} /${marks(q.max_marks)}`)),
        h("th", { scope: "col", class: "num" }, "Total"))),
      h("tbody", {}, results.rows.map((row) => h("tr", {},
        h("th", { scope: "row" }, studentCell(row)),
        results.questions.map((q) => gradeCell(row.cells[q.number], q)),
        h("td", { class: "num" }, row.total == null ? h("span", { class: "muted" }, statusWord(row.status)) : `${marks(row.total)} / ${marks(row.max)}`)))))));
}


function studentCell(row) {
  if (row.student_id) return [row.name, h("span", { class: "student-id" }, row.student_id)];
  if (row.status === "queued" || row.status === "reading") return h("span", { class: "muted" }, "Reading sheet…");
  const label = [h("span", { class: "pill flag" }, "Unmatched sheet"),
    h("span", { class: "student-id" }, row.read_student_id ? `ID read as ${row.read_student_id}` : "No ID found on the sheet")];
  if (exam.status !== "ready") return label;
  if (!exam.roster_size) return [...label, h("span", { class: "student-id" }, "This exam has no roster yet. Use Add students, and sheets will match by ID.")];
  if (!results.unassigned_students.length) return [...label, h("span", { class: "student-id" }, "Everyone on the roster has a sheet. Add this student to the roster to assign it.")];
  const select = h("select", { "aria-label": "Assign a student" },
    h("option", { value: "" }, "Choose student"),
    results.unassigned_students.map((s) => h("option", { value: s.student_id }, `${s.name} (${s.student_id})`)));
  const button = h("button", {
    onclick: async () => {
      if (!select.value) return;
      await busy(button, "…", () => api(`/api/submissions/${row.submission_id}/student`, { method: "PUT", body: { student_id: select.value } }));
      await refreshLive();
    },
  }, "Assign");
  return [...label, h("div", { class: "assign" }, select, button)];
}

function gradeCell(cell, q) {
  if (!cell) return h("td", { class: "num muted" }, "–");
  if (cell.status === "failed") return h("td", { class: "num" }, h("button", { class: "cell failed", onclick: () => openAnswer(cell.answer_id) }, "Failed"));
  if (cell.status !== "graded") return h("td", { class: "num muted", title: "Grading" }, "…");
  const classes = ["cell", cell.flagged && "flagged", cell.overridden && "overridden"].filter(Boolean).join(" ");
  return h("td", { class: "num" }, h("button", {
    class: classes, "data-answer": cell.answer_id, onclick: () => openAnswer(cell.answer_id),
    "aria-label": `Question ${q.number}: ${marks(cell.marks)} of ${marks(cell.max_marks)}${cell.flagged ? ", flagged" : ""}`,
  }, marks(cell.marks)));
}

async function refreshLive(fresh = []) {
  results = await api(`/api/exams/${exam.exam_id}/results`);
  const next = { sheets: sheetsSection(), grades: gradesSection() };
  live.sheets.replaceWith(next.sheets);
  live.grades.replaceWith(next.grades);
  live = next;
  fresh.forEach((id) => main.querySelector(`[data-answer="${id}"]`)?.classList.add("fresh"));
}

function listen(id) {
  events?.close();
  let pending = [];
  let timer = null;
  events = new EventSource(`/api/exams/${id}/events?token=${encodeURIComponent(token())}`);
  events.addEventListener("grade", (event) => {
    pending.push(JSON.parse(event.data).answer_id);
    clearTimeout(timer);
    timer = setTimeout(() => { refreshLive(pending); pending = []; loadExams(); }, 400);
  });
}

async function openAnswer(answerId) {
  const a = await api(`/api/answers/${answerId}`);
  const grade = a.grade;
  const shown = grade ? (grade.override_marks ?? grade.final_marks) : null;
  panel.replaceChildren(...[
    h("div", { class: "panel-head" },
      h("div", {}, h("p", { class: "muted small" }, a.student ? `${a.student.name} (${a.student.student_id})` : "Unmatched sheet"), h("h2", {}, `Question ${a.question.number}`)),
      h("button", { class: "icon", "aria-label": "Close", onclick: closePanel }, "×")),
    grade?.flagged ? h("p", { class: "flag-note" }, `Flagged: ${grade.flag_reasons.join(", ")}.`) : null,
    a.status === "failed" ? h("p", { class: "flag-note" }, "The judges couldn't grade this answer after several tries. Set the mark yourself below.") : null,
    a.question.text ? h("p", { class: "question-text" }, a.question.text) : null,
    h("div", { class: "section" },
      h("h3", {}, "Student's answer"),
      h("blockquote", { class: "answer" }, a.text || "No answer was found on the sheet."),
      h("p", { class: "muted small" },
        a.read_confidence != null ? `Read with ${Math.round(a.read_confidence * 100)}% confidence. ` : "",
        h("a", { href: a.scan_url, target: "_blank", rel: "noopener" }, "Open the full scan")),
      a.scan_type.startsWith("image/") ? h("img", { class: "scan", src: a.scan_url, alt: "Scanned answer sheet" }) : null),
    h("div", { class: "section" },
      h("div", { class: "section-head" }, h("h3", {}, "Rubric"), shown != null ? h("span", { class: "score" }, `${marks(shown)} / ${marks(a.question.max_marks)}`) : null),
      h("table", { class: "judges" },
        h("thead", {}, h("tr", {}, h("th", {}, "Point"), JUDGES.map(([, label]) => h("th", { class: "num" }, label)), h("th", { class: "num" }, "Final"))),
        h("tbody", {}, a.points.map((p) => h("tr", {},
          h("td", {}, p.description, p.evidence ? h("div", { class: "evidence" }, `“${p.evidence}”`) : null),
          JUDGES.map(([key]) => h("td", { class: "num" }, marks(p.judges[key]))),
          h("td", { class: "num" }, h("strong", {}, marks(p.final)), h("span", { class: "muted" }, ` /${marks(p.marks)}`)))))),
      grade?.override_marks != null ? h("p", { class: "muted small" }, `You set this mark. The judges gave ${marks(grade.final_marks)}.`) : null),
    webEvidence(a.web_evidence),
    a.feedback ? h("div", { class: "section" }, h("h3", {}, "Feedback for the student"), h("p", {}, a.feedback)) : null,
    a.exam_status === "draft" ? null : overrideForm(a, shown),
  ].filter(Boolean));
  panel.classList.add("open");
  panel.querySelector("button").focus();
}

function webEvidence(web) {
  if (!web?.summary) return null;
  return h("div", { class: "section" },
    h("h3", {}, "Web check"),
    h("p", {}, web.summary),
    web.sources?.length ? h("ul", { class: "sources" }, web.sources.map((url) => h("li", {}, h("a", { href: url, target: "_blank", rel: "noopener" }, new URL(url).hostname)))) : null);
}

function overrideForm(a, shown) {
  const input = h("input", { type: "number", class: "num", min: 0, max: a.question.max_marks, step: 0.5, value: shown ?? "" });
  const save = h("button", {
    class: "primary",
    onclick: async () => {
      await busy(save, "Saving…", () => api(`/api/answers/${a.answer_id}/grade`, { method: "PUT", body: { marks: Number(input.value) } }));
      toast("Mark saved");
      await openAnswer(a.answer_id);
      await refreshLive([a.answer_id]);
    },
  }, "Save mark");
  const clear = a.grade?.override_marks != null && a.grade.judges > 0 ? h("button", {
    onclick: async () => {
      await api(`/api/answers/${a.answer_id}/grade`, { method: "PUT", body: { marks: null } });
      await openAnswer(a.answer_id);
      await refreshLive([a.answer_id]);
    },
  }, "Use the judges' mark") : null;
  return h("div", { class: "section" }, h("h3", {}, "Change the mark"),
    h("div", { class: "override" }, h("label", {}, `Marks out of ${marks(a.question.max_marks)}`, input), save, clear));
}

function closePanel() {
  panel.classList.remove("open");
}

function regrades() {
  const section = h("section", { class: "section" }, h("h2", {}, "Regrade requests"));
  api(`/api/exams/${exam.exam_id}/regrades`).then((requests) => {
    if (!requests.length) return section.append(h("p", { class: "muted" }, "No students have asked for a regrade."));
    section.append(h("ul", { class: "requests" }, requests.map((r) => {
      const input = h("input", { type: "number", class: "num", min: 0, step: 0.5, "aria-label": "New mark" });
      const resolve = h("button", {
        onclick: async () => {
          await busy(resolve, "Saving…", () => api(`/api/regrades/${r.request_id}/resolve`, { method: "POST", body: { marks: input.value === "" ? null : Number(input.value) } }));
          await reload();
        },
      }, input.value === "" ? "Keep mark and close" : "Save and close");
      input.addEventListener("input", () => { resolve.textContent = input.value === "" ? "Keep mark and close" : "Save and close"; });
      return h("li", { class: "card request" },
        h("div", { class: "section-head" }, h("strong", {}, `${r.name}, question ${r.number}`), h("span", { class: `pill ${r.status === "open" ? "flag" : "good"}` }, r.status === "open" ? "Open" : "Resolved")),
        h("p", {}, r.reason),
        r.status === "open" ? h("div", { class: "request-actions" },
          h("button", { class: "link", onclick: () => openAnswer(r.answer_id) }, "View answer"), input, resolve) : null);
    })));
  });
  return section;
}

function stats() {
  const section = h("section", { class: "section" });
  api(`/api/exams/${exam.exam_id}/stats`).then(({ questions, judges }) => {
    if (!questions.length) return section.remove();
    section.append(
      h("div", { class: "section-head" }, h("h2", {}, "Class report"), h("p", { class: "muted small" }, `Updated nightly. Last run ${new Date(questions[0].computed_at).toLocaleString()}.`)),
      h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, h("th", {}, "Question"), h("th", { class: "num" }, "Average score"), h("th", { class: "num" }, "Spread"), h("th", { class: "num" }, "Flagged"))),
        h("tbody", {}, questions.map((q) => h("tr", {}, h("td", {}, `Q${q.number}`),
          h("td", { class: "num" }, `${Math.round(q.mean_score * 100)}%`), h("td", { class: "num" }, marks(q.stddev)),
          h("td", { class: "num" }, `${Math.round(q.flag_rate * 100)}%`)))))),
      judges.length ? h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, h("th", {}, "Judge"), h("th", { class: "num" }, "Average gap from final mark"), h("th", { class: "num" }, "Within 1 mark"))),
        h("tbody", {}, judges.map((j) => h("tr", {}, h("td", {}, Object.fromEntries(JUDGES)[j.model] ?? j.model),
          h("td", { class: "num" }, marks(j.mean_gap)), h("td", { class: "num" }, `${Math.round(j.within_one * 100)}%`))))))
        : null);
  });
  return section;
}

async function release() {
  if (!confirm("Release results? Every student on the roster will be able to see their marks and feedback.")) return;
  try {
    await api(`/api/exams/${exam.exam_id}/release`, { method: "POST" });
    toast("Results released");
    events?.close();
    await reload();
  } catch (error) {
    toast(error.message, "bad");
  }
}

async function exportCsv() {
  const response = await fetch(`/api/exams/${exam.exam_id}/export`, { headers: { Authorization: `Bearer ${token()}` } });
  const link = h("a", { href: URL.createObjectURL(await response.blob()), download: `${exam.title}.csv` });
  link.click();
  URL.revokeObjectURL(link.href);
}
