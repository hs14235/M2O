import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import type { User, Workspace } from "./types";
import { ErrorNotice } from "./components/Feedback";
import { primaryPage, routePath, settingsPath, settingsSection, useNavigation } from "./navigation";
import { DepartmentHero, DepartmentSwitch, useMotionPreference } from "./components/DepartmentExperience";
import DemoEntry from "./components/DemoEntry";
import AccessPortal from "./components/AccessPortal";
import { captureAccessLink, clearCapturedAccessLink } from "./access-link";
import { ChromeControls, ChromeRegion, useShellChrome } from "./components/ShellChrome";

const Workbench = lazy(() => import("./components/Workbench"));
const SettingsPage = lazy(() => import("./components/SettingsPage"));
const AuditPage = lazy(() => import("./components/AuditPage"));
const DailyPlanner = lazy(() => import("./components/DailyPlanner"));

export default function App() {
  const [user, setUser] = useState<User | null>(null), [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [checking, setChecking] = useState(true), [error, setError] = useState<unknown>(null), [notice, setNotice] = useState("");
  const dirty = useRef(false);
  const [accessLink, setAccessLink] = useState(captureAccessLink);
  const motion = useMotionPreference();
  const chrome = useShellChrome();
  const { route, path, navigate } = useNavigation(() => {
    if (dirty.current && !window.confirm("Discard unsaved transcript or outcome edits?")) return false;
    dirty.current = false; return true;
  });
  const onDirty = useCallback((value: boolean) => { dirty.current = value; }, []);
  useEffect(() => {
    clearCapturedAccessLink();
    const capture = () => { setAccessLink(captureAccessLink()); clearCapturedAccessLink(); };
    window.addEventListener("hashchange", capture); return () => window.removeEventListener("hashchange", capture);
  }, []);
  async function refreshUser(signal?: AbortSignal) {
    const [account, spaces] = await Promise.all([api<User>("/me", { signal }), api<Workspace[]>("/workspaces", { signal })]);
    setUser(account); setWorkspaces(spaces);
  }
  useEffect(() => {
    const controller = new AbortController();
    refreshUser(controller.signal).catch(e => { if (!controller.signal.aborted && !(e instanceof ApiError && e.status === 401)) setError(e); }).finally(() => { if (!controller.signal.aborted) setChecking(false); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (user && path === "/" && workspaces[0]) navigate(routePath(workspaces[0].id), true);
  }, [user, path, workspaces, navigate]);
  useEffect(() => {
    if (!user) return;
    document.title = (route.page === "meetings" && route.meeting ? route.step[0].toUpperCase() + route.step.slice(1) : route.page[0].toUpperCase() + route.page.slice(1)) + " · Meeting to outcomes";
    document.getElementById("main")?.focus(); window.scrollTo({ top: 0, behavior: "instant" });
  }, [path, user, route.page, route.meeting, route.step]);
  useEffect(() => {
    const handler = (event: BeforeUnloadEvent) => { if (dirty.current) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("beforeunload", handler); return () => window.removeEventListener("beforeunload", handler);
  }, []);
  useEffect(() => {
    if (!user) return;
    const expire = () => { setUser(null); setWorkspaces([]); dirty.current = false; setError(new Error(user.is_visitor ? "Your temporary demo access has ended. Start a fresh isolated demo to explore again." : "Your session has ended. Sign in again to continue.")); };
    window.addEventListener("m2o:session-expired", expire);
    return () => window.removeEventListener("m2o:session-expired", expire);
  }, [user?.id, user?.is_visitor]);
  function mayLeave() { return !dirty.current || window.confirm("Discard unsaved transcript or outcome edits?"); }
  async function logout() {
    if (!mayLeave()) return;
    try { await api("/auth/logout", { method: "POST" }); setUser(null); dirty.current = false; } catch (e) { setError(e); }
  }
  const workspace = workspaces.find(w => w.id === route.workspace);
  useEffect(() => { document.documentElement.dataset.department = workspace?.department || "engineering"; }, [workspace?.department]);
  if (checking) return <main className="login"><p role="status">Checking your session…</p></main>;
  const accessPath = path.split("?")[0];
  if (accessPath === "/invite" || accessPath === "/recover") return <AccessPortal key={accessPath} path={accessPath} initialToken={accessLink?.path === accessPath ? accessLink.token : ""} user={user} onAuthenticated={refreshUser} onSignOut={async () => { await api("/auth/logout", { method: "POST" }); setUser(null); setWorkspaces([]); dirty.current = false; }} onAccountReset={() => { setUser(null); setWorkspaces([]); dirty.current = false; }} onTokenUsed={() => setAccessLink(null)} onContinue={id => { setAccessLink(null); navigate(id ? routePath(id) : "/", true); }} />;
  if (!user) return <Login onLogin={async () => { await refreshUser(); setError(null); setNotice(""); dirty.current = false; navigate("/", true); }} error={error} notice={notice} calm={motion.calm} onToggleMotion={motion.toggle} reduced={motion.reduced} />;
  const section = settingsSection(route), active = primaryPage(route);
  const accountErased = () => { setUser(null); setWorkspaces([]); dirty.current = false; setError(null); setNotice("Your account was deactivated and anonymized. Shared workspace content remains with its workspace."); navigate("/", true); };
  const auditAllowed = Boolean(workspace && ["owner", "reviewer"].includes(workspace.role));
  return <>
    <a className="skip-link" href="#main">Skip to workspace</a>
    <ChromeControls {...chrome} />
    <ChromeRegion id="workspace-header" expanded={chrome.header} calm={motion.calm}>
      <header className="app-header"><a className="brand" href="#main"><span aria-hidden="true" className="brand-mark">M2O</span><span>Meeting <strong>2 Outcomes</strong></span></a><div className="account"><button className="motion-control" aria-pressed={motion.calm} disabled={motion.reduced} onClick={motion.toggle}>{motion.reduced ? "Reduced motion active" : motion.calm ? "Calm mode on" : "Enable calm mode"}</button><span>{user.name}</span><button className="quiet" onClick={logout}>Sign out</button></div></header>
    </ChromeRegion>
    <div className="app-shell" data-sidebar={chrome.sidebar ? "open" : "closed"}>
      <ChromeRegion id="workspace-sidebar" expanded={chrome.sidebar} calm={motion.calm} side>
        <aside className="app-nav" aria-label="Workspace sidebar"><DepartmentSwitch workspaces={workspaces} active={workspace} onChange={id => navigate(routePath(id))} /><label>Workspace<select value={workspace?.id || ""} onChange={event => navigate(routePath(event.target.value))}>{!workspace && <option value="">Choose workspace</option>}{workspaces.map(value => <option key={value.id} value={value.id}>{value.name}</option>)}</select></label>
          <nav aria-label="Workspace pages">{workspace && [{ id: "plan", name: "My day", path: routePath(workspace.id, "plan") }, { id: "meetings", name: "Meetings", path: routePath(workspace.id) }, { id: "audit", name: "Audit", path: routePath(workspace.id, "audit") }, { id: "settings", name: "Settings", path: settingsPath(workspace.id) }].map(item => item.id === "audit" && !auditAllowed ? <button key={item.id} disabled aria-describedby="audit-permission">Audit</button> : <a key={item.id} href={item.path} aria-current={active === item.id ? "page" : undefined} className={active === item.id ? "active" : ""} onClick={event => { if (!event.ctrlKey && !event.metaKey && !event.shiftKey && event.button === 0) { event.preventDefault(); navigate(item.path); } }}>{item.name}</a>)}</nav>
          {workspace && !auditAllowed && <p className="muted" id="audit-permission">Audit requires owner or reviewer authority.</p>}{workspace && !user.is_visitor && <p className="muted">Your role: <strong>{workspace.role}</strong></p>}<p className="local-note">Source-linked outcomes<br />Review before sharing</p>
        </aside>
      </ChromeRegion>
      <main id="main" tabIndex={-1}>
        {workspace && <DepartmentHero workspace={workspace} calm={motion.calm} compact={route.page !== "meetings" || Boolean(route.meeting)} />}
        <ErrorNotice error={error} />
        {user.is_visitor && <section className="notice visitor-banner" aria-label="Synthetic demo session"><strong>Your isolated synthetic demo</strong><p>Use synthetic data. Your reviews and plan are isolated; real uploads and external sends are disabled.</p>{user.expires_at && <details><summary>Demo access ends <time dateTime={user.expires_at}>{new Date(user.expires_at).toLocaleString()}</time></summary><p>When access expires, start a fresh demo. Access expiry does not immediately erase stored data.</p></details>}</section>}
        <Suspense fallback={<p role="status">Loading workspace…</p>}>
          {!route.valid ? <section className="panel"><h1>Page not found</h1><p>Choose a workspace to return to your meetings.</p></section>
            : section && route.workspace ? <SettingsPage key={route.workspace} workspaceId={route.workspace} workspace={workspace} section={section} user={user} navigate={navigate} onDirty={onDirty} refreshUser={refreshUser} onAccountErased={accountErased} motion={motion} chrome={chrome} />
            : workspace ? route.page === "plan" ? <DailyPlanner key={workspace.id} workspace={workspace} navigate={navigate} />
              : route.page === "audit" ? <AuditPage key={workspace.id} workspace={workspace} />
              : <Workbench key={workspace.id} workspace={workspace} user={user} onDirty={onDirty} route={route} navigate={navigate} />
            : workspaces.length ? <section className="panel"><h1>Choose an accessible workspace</h1><p>This workspace is not available to your account.</p></section>
            : user.is_visitor ? <section className="panel"><h1>Demo access is unavailable</h1><p>Sign out and start a fresh demo. Visitors cannot create private workspaces.</p></section>
            : <CreateWorkspace onCreated={() => refreshUser().catch(setError)} />}
        </Suspense>
      </main>
    </div>
  </>;

}

function Login({ onLogin, error, notice, calm, onToggleMotion, reduced }: { onLogin: () => Promise<void>; error: unknown; notice: string; calm: boolean; onToggleMotion: () => void; reduced: boolean }) {
  const [email, setEmail] = useState(""), [password, setPassword] = useState(""), [failure, setFailure] = useState<unknown>(null), [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setFailure(null);
    try { await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }); setPassword(""); await onLogin(); } catch (e) { setFailure(e); } finally { setBusy(false); }
  }
  return <main className="login"><section className="login-story"><span className="eyebrow">M2O · Meeting 2 Outcomes</span><h1>A useful meeting<br />has a clear next step.</h1><p>Capture actions, decisions, blockers and risks. Confirm the people involved. Keep every outcome connected to its source.</p><div className="pill-row"><span>Engineering</span><span>People operations</span><span>Finance</span></div></section><section className="panel login-form"><DemoEntry onStarted={onLogin} /><h2>Sign in to your workspace</h2><p>Use your invited private account, or the account created during local setup.</p><form onSubmit={submit}><fieldset disabled={busy}><legend className="sr-only">Sign-in credentials</legend><label>Email<input required type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)} /></label><label>Password<input required type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} /></label><button className="primary">Sign in</button></fieldset></form><ErrorNotice error={failure || error} />{notice && <p role="status" className="notice">{notice}</p>}<p className="muted">Invited accounts sign in here. If you need help returning, recovery is operator assisted.</p><a href="/recover">Recover account access</a><button aria-pressed={calm} disabled={reduced} onClick={onToggleMotion}>{reduced ? "Reduced motion active" : calm ? "Calm mode on" : "Enable calm mode"}</button></section></main>;
}

function CreateWorkspace({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState(""), [department, setDepartment] = useState("engineering"), [error, setError] = useState<unknown>(null);
  async function create(e: React.FormEvent) { e.preventDefault(); try { await api("/workspaces", { method: "POST", body: JSON.stringify({ name, department }) }); onCreated(); } catch (e) { setError(e); } }
  return <section className="panel"><h1>Create your first workspace</h1><form onSubmit={create}><label>Name<input required value={name} onChange={e => setName(e.target.value)} /></label><label>Department<select value={department} onChange={e => setDepartment(e.target.value)}>{["engineering", "hr", "finance"].map(d => <option key={d}>{d}</option>)}</select></label><button className="primary">Create workspace</button></form><ErrorNotice error={error} /></section>;
}
