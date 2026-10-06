import { errorMessage } from "../api";

export function ErrorNotice({ error }: { error: unknown }) {
  return error ? <p role="alert" className="notice error">{errorMessage(error)}</p> : null;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="empty">{children}</div>;
}
