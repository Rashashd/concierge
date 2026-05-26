type LoaderConfig = {
  apiBase: string;
  widgetId: string;
  widgetUrl: string;
  position: "left" | "right";
};

const SCRIPT_SELECTOR = "script[data-widget-id]";

function readConfig(): LoaderConfig {
  const script = document.currentScript ?? document.querySelector(SCRIPT_SELECTOR);
  if (!(script instanceof HTMLScriptElement)) {
    throw new Error("Concierge loader script was not found.");
  }

  const widgetId = script.dataset.widgetId;
  if (!widgetId) {
    throw new Error("Concierge widget requires data-widget-id.");
  }

  const scriptUrl = new URL(script.src, window.location.href);
  const widgetUrl =
    script.dataset.widgetUrl ?? new URL("widget.html", scriptUrl).toString();
  const apiBase = script.dataset.apiBase ?? window.location.origin;
  const position = script.dataset.position === "left" ? "left" : "right";

  return { apiBase, widgetId, widgetUrl, position };
}

function mountFrame(config: LoaderConfig): void {
  const frame = document.createElement("iframe");
  const url = new URL(config.widgetUrl, window.location.href);
  url.searchParams.set("apiBase", config.apiBase);
  url.searchParams.set("widgetId", config.widgetId);

  frame.src = url.toString();
  frame.title = "Concierge chat";
  frame.setAttribute("aria-label", "Concierge chat");
  frame.style.position = "fixed";
  frame.style.bottom = "20px";
  frame.style[config.position] = "20px";
  frame.style.width = "min(380px, calc(100vw - 32px))";
  frame.style.height = "620px";
  frame.style.maxHeight = "calc(100vh - 32px)";
  frame.style.border = "0";
  frame.style.borderRadius = "18px";
  frame.style.zIndex = "2147483647";
  frame.style.colorScheme = "light";
  frame.style.boxShadow = "0 24px 70px rgba(23, 29, 36, 0.22)";

  document.body.appendChild(frame);
}

mountFrame(readConfig());
