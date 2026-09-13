import { useEffect, useSyncExternalStore } from 'react';
import App from './App';
import { auth, authConfigurationError } from './auth';

export function AuthGate() {
  const session = useSyncExternalStore(auth.subscribe, auth.getSnapshot);
  useEffect(() => {
    if (!authConfigurationError) void auth.initialize();
  }, []);
  if (!authConfigurationError && session.status === 'ready')
    return (
      <App
        principal={session.principal}
        onLogout={auth.config.mode === 'cognito' ? auth.logout : undefined}
      />
    );
  return (
    <main className="auth-panel">
      <p className="eyebrow">PCB INSPECTOR AI</p>
      <h1>
        {session.status === 'loading' && !authConfigurationError
          ? 'Opening your workspace'
          : 'Your inspection workspace'}
      </h1>
      {authConfigurationError || session.message ? (
        <p role="alert">{authConfigurationError || session.message}</p>
      ) : (
        <p role="status">
          {session.status === 'loading'
            ? 'Checking your session…'
            : 'Sign in to upload boards and review your inspections.'}
        </p>
      )}
      {!authConfigurationError && session.status !== 'loading' && (
        <button className="button primary" onClick={() => void auth.login()}>
          {auth.config.mode === 'cognito' ? 'Sign in or create an account' : 'Retry connection'}
        </button>
      )}
    </main>
  );
}
