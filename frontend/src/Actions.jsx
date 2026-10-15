import React, {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

const FormPending = createContext(false);
const GroupPending = createContext(null);

export function ActionGroup({ as: Tag = "div", children, ...props }) {
  const [pending, setPending] = useState(false);
  return (
    <Tag {...props}>
      <GroupPending.Provider value={{ pending, setPending }}>
        {children}
      </GroupPending.Provider>
    </Tag>
  );
}
// Scope exists only for synchronous event dispatch. The promise keeps its own
// receiver; effects, timers and concurrent requests never inherit an action.
let receiver = null;
function dispatch(receive, handler, event) {
  const previous = receiver;
  receiver = receive;
  try {
    return handler?.(event);
  } finally {
    receiver = previous;
  }
}

export async function performAction(task, loadError) {
  const receive = loadError ? null : receiver;
  receive?.({ pending: true, error: "", notice: "" });
  try {
    await task();
    receive?.({ pending: false, error: "", notice: "Done." });
  } catch (error) {
    if (receive) receive({ pending: false, error: error.message, notice: "" });
    else if (loadError) loadError(error);
    else throw error;
  }
}

function useFeedback() {
  const [state, setState] = useState({ pending: false, error: "", notice: "" });
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const receive = (next) => {
    if (mounted.current) setState(next);
  };
  useEffect(() => {
    if (!state.notice) return;
    const timer = setTimeout(
      () => setState((s) => ({ ...s, notice: "" })),
      4000,
    );
    return () => clearTimeout(timer);
  }, [state.notice]);
  return [state, receive];
}
function Feedback({ state }) {
  return (
    <>
      {state.pending && (
        <span className="action-status" role="status">
          Saving…
        </span>
      )}
      {state.error && (
        <span className="action-error" role="alert">
          {state.error}
        </span>
      )}
      {state.notice && (
        <span className="action-status" role="status">
          {state.notice}
        </span>
      )}
    </>
  );
}
export function ActionForm({
  onSubmit,
  children,
  success = "Saved.",
  ...props
}) {
  const [state, receive] = useFeedback();
  return (
    <form
      {...props}
      aria-busy={state.pending}
      onSubmit={(e) => {
        if (state.pending) {
          e.preventDefault();
          return;
        }
        dispatch(
          (next) => receive({ ...next, notice: next.notice ? success : "" }),
          onSubmit,
          e,
        );
      }}
    >
      <FormPending.Provider value={state.pending}>
        {children}
      </FormPending.Provider>
      <Feedback state={state} />
    </form>
  );
}
function control(tag) {
  return function ActionControl({
    onClick,
    onChange,
    onBlur,
    disabled,
    children,
    success = "Done.",
    ...props
  }) {
    const [state, receive] = useFeedback();
    const formPending = useContext(FormPending);
    const group = useContext(GroupPending);
    const receiveLocal = (next) => {
      receive({ ...next, notice: next.notice ? success : "" });
      group?.setPending(next.pending);
    };
    const pending =
      state.pending ||
      (formPending && tag === "button" && props.type !== "button");
    const events = {};
    for (const [name, handler] of Object.entries({
      onClick,
      onChange,
      onBlur,
    })) {
      if (handler) events[name] = (e) => dispatch(receiveLocal, handler, e);
    }
    return (
      <>
        {React.createElement(
          tag,
          {
            ...props,
            ...events,
            disabled:
              disabled || state.pending || formPending || group?.pending,
            "aria-busy": pending || undefined,
          },
          ["input", "textarea"].includes(tag) ? undefined : (
            <>
              {pending && tag === "button" ? "Saving… " : ""}
              {children}
            </>
          ),
        )}
        <Feedback state={state} />
      </>
    );
  };
}
export const ActionButton = control("button");
export const ActionInput = control("input");
export const ActionSelect = control("select");
export const ActionTextarea = control("textarea");
