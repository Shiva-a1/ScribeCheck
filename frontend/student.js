import { api, busy, currentUser, h, marks, toast } from "./app.js";

const main = document.querySelector("#main");
const user = await currentUser();
window.addEventListener("hashchange", route);
await route();

async function route() {
  const id = Number(new URLSearchParams(location.hash.slice(1)).get("exam"));
  try {
    main.replaceChildren(h("div", { class: "page student-page" }, id ? await examPage(id) : await listPage()));
  } catch (error) {
    main.replaceChildren(h("div", { class: "page student-page" }, h("p", { class: "error" }, error.message)));
  }
}

async function listPage() {
  const exams = await api("/api/student/exams");
  return [
    h("div", { class: "title" }, h("h1", {}, user.name ? `Your results, ${user.name.split(" ")[0]}` : "Your results")),
    exams.length
      ? h("div", { class: "section" }, exams.map((e) => h("a", { class: "card exam-card", href: `#exam=${e.exam_id}` },
          h("div", {}, h("h2", {}, e.title), h("p", { class: "muted small" }, `Released ${new Date(e.released_at).toLocaleDateString()}`)),
          h("span", { class: "score" }, `${marks(e.total)} / ${marks(e.max)}`))))
      : h("p", { class: "empty" }, "Your teacher hasn't released any results yet. They'll appear here when they do."),
  ];
}

async function examPage(id) {
  const exam = await api(`/api/student/exams/${id}`);
  return [
    h("div", {}, h("a", { href: "#", class: "small" }, "All results")),
    h("div", { class: "page-head" },
      h("div", { class: "title" }, h("h1", {}, exam.title), h("a", { href: exam.scan_url, target: "_blank", rel: "noopener", class: "small" }, "View your scanned sheet")),
      h("span", { class: "score" }, `${marks(exam.total)} / ${marks(exam.max)}`)),
    exam.questions.map((q) => question(q)),
  ];
}

function question(q) {
  return h("article", { class: "card result" },
    h("div", { class: "result-head" }, h("h2", {}, `Question ${q.number}`), h("span", { class: "score" }, `${marks(q.marks)} / ${marks(q.max_marks)}`)),
    q.text ? h("p", { class: "question-text" }, q.text) : null,
    h("div", { class: "section" }, h("h3", {}, "Your answer"), h("blockquote", { class: "answer" }, q.answer || "No answer was found for this question.")),
    q.points.length ? h("div", { class: "section" }, h("h3", {}, "What the marks were for"),
      h("ul", { class: "checklist" }, q.points.map((p) => {
        const earned = Number(p.marks) >= Number(p.max);
        const partly = !earned && Number(p.marks) > 0;
        return h("li", { class: earned || partly ? "earned" : "missed" },
          h("span", { "aria-hidden": "true" }, earned ? "✓" : partly ? "◐" : "○"),
          h("span", {}, p.description, h("span", { class: "visually-hidden" }, earned ? " (earned)" : partly ? " (partly earned)" : " (missed)")),
          h("span", { class: "muted" }, `${marks(p.marks)} / ${marks(p.max)}`));
      }))) : null,
    q.adjusted ? h("p", { class: "muted small" }, "Your teacher adjusted this mark.") : null,
    q.feedback ? h("div", { class: "section" }, h("h3", {}, "How to improve"), h("p", { class: "feedback" }, q.feedback)) : null,
    regrade(q));
}

function regrade(q) {
  if (q.regrade_status) {
    return h("p", { class: "muted small" }, q.regrade_status === "open" ? "You asked for a regrade. Your teacher will review it." : "Your teacher reviewed your regrade request.");
  }
  const holder = h("div");
  const open = h("button", { class: "link", onclick: () => holder.replaceChildren(form()) }, "Ask for a regrade");
  holder.append(open);

  function form() {
    const reason = h("textarea", { rows: 3, required: true, minlength: 10, placeholder: "Explain which part of your answer you think was missed." });
    return h("form", {
      class: "section",
      onsubmit: async (event) => {
        event.preventDefault();
        await busy(event.submitter, "Sending…", () => api(`/api/student/answers/${q.answer_id}/regrade`, { method: "POST", body: { reason: reason.value } }));
        toast("Request sent to your teacher");
        await route();
      },
    }, h("label", {}, "Why should this be regraded?", reason), h("div", { class: "actions" }, h("button", { class: "primary", type: "submit" }, "Send request")));
  }
  return holder;
}
