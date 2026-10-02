import { api, ApiError, h, setToken, token } from "./app.js";

const root = document.querySelector("#signin");
const config = await fetch("/api/config").then((r) => r.json());
const redirect = `${location.origin}/`;

async function goHome() {
  try {
    const user = await api("/api/me");
    location.href = user.role === "student" ? "/student.html" : "/teacher.html";
  } catch (error) {
    sessionStorage.clear();
    render(error instanceof ApiError ? error.message : "Sign-in failed. Try again.");
  }
}

const base64url = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

async function startCognito() {
  const verifier = base64url(crypto.getRandomValues(new Uint8Array(32)));
  sessionStorage.setItem("pkce", verifier);
  const challenge = base64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
  const url = new URL(`https://${config.cognito_domain}/oauth2/authorize`);
  url.search = new URLSearchParams({
    response_type: "code", client_id: config.cognito_client_id, redirect_uri: redirect,
    scope: "openid email", code_challenge_method: "S256", code_challenge: challenge,
  });
  location.href = url;
}

async function finishCognito(code) {
  history.replaceState(null, "", "/");
  const response = await fetch(`https://${config.cognito_domain}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code", client_id: config.cognito_client_id, code,
      redirect_uri: redirect, code_verifier: sessionStorage.getItem("pkce") ?? "",
    }),
  });
  const tokens = await response.json();
  if (!tokens.id_token) return render("Sign-in didn't complete. Try again.");
  setToken(tokens.id_token);
  await goHome();
}

function render(message = "") {
  const error = h("p", { class: "error", role: "alert" }, message);
  if (config.auth_mode === "cognito") {
    root.replaceChildren(
      h("h2", {}, "Sign in"),
      h("p", { class: "muted" }, "Use the school account your teacher or administrator invited."),
      h("button", { class: "primary", onclick: startCognito }, "Sign in with your school account"),
      error,
    );
    return;
  }
  const email = h("input", { type: "email", name: "email", required: true, autocomplete: "email", placeholder: "name@ufl.edu" });
  root.replaceChildren(
    h("h2", {}, "Sign in"),
    h("form", {
      onsubmit: async (event) => {
        event.preventDefault();
        const { token: issued } = await api("/api/dev/login", { method: "POST", body: { email: email.value } });
        setToken(issued);
        await goHome();
      },
    }, h("label", {}, "Email", email), h("button", { class: "primary", type: "submit" }, "Sign in"), error),
    h("p", { class: "muted small" }, "Development sign-in: any invited email works without a password. Switch AUTH_MODE to cognito before deploying."),
  );
}

const code = new URLSearchParams(location.search).get("code");
if (code) await finishCognito(code);
else if (token()) await goHome();
else render();
