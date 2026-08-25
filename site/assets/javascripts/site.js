(function () {
  "use strict";

  const siteScriptUrl = document.currentScript?.src ||
    Array.from(document.scripts).find((script) => /\/site\.js(?:\?|$)/.test(script.src))?.src ||
    "";

  const state = {
    article: null,
    frameRequested: false,
    lightbox: null,
    mermaidQueue: Promise.resolve(),
    mermaidRuntimePromise: null,
    observedScheme: null,
  };

  function ensureProgressBar() {
    let progress = document.getElementById("reading-progress");
    if (progress) return progress;

    progress = document.createElement("div");
    progress.id = "reading-progress";
    progress.setAttribute("role", "progressbar");
    progress.setAttribute("aria-label", "文章阅读进度");
    progress.setAttribute("aria-valuemin", "0");
    progress.setAttribute("aria-valuemax", "100");
    progress.setAttribute("aria-valuenow", "0");
    document.body.append(progress);
    return progress;
  }

  function updateReadingProgress() {
    state.frameRequested = false;

    const progress = ensureProgressBar();
    const article = state.article;
    if (!article) {
      progress.style.setProperty("--reading-progress", "0");
      progress.setAttribute("aria-valuenow", "0");
      return;
    }

    const rect = article.getBoundingClientRect();
    const articleTop = window.scrollY + rect.top;
    const readableDistance = Math.max(article.offsetHeight - window.innerHeight, 1);
    const ratio = Math.min(Math.max((window.scrollY - articleTop) / readableDistance, 0), 1);
    const percentage = Math.round(ratio * 100);

    progress.style.setProperty("--reading-progress", ratio.toFixed(4));
    progress.setAttribute("aria-valuenow", String(percentage));
  }

  function requestProgressUpdate() {
    if (state.frameRequested) return;
    state.frameRequested = true;
    window.requestAnimationFrame(updateReadingProgress);
  }

  function ensureLightbox() {
    if (state.lightbox && document.body.contains(state.lightbox)) return state.lightbox;

    const dialog = document.createElement("dialog");
    dialog.className = "image-lightbox";
    dialog.setAttribute("aria-label", "图片大图预览");

    const frame = document.createElement("div");
    frame.className = "image-lightbox__frame";

    const image = document.createElement("img");
    image.className = "image-lightbox__image";
    image.alt = "";

    const caption = document.createElement("div");
    caption.className = "image-lightbox__caption";
    caption.setAttribute("aria-live", "polite");

    const close = document.createElement("button");
    close.className = "image-lightbox__close";
    close.type = "button";
    close.setAttribute("aria-label", "关闭大图");
    close.title = "关闭大图";
    close.textContent = "\u00d7";

    frame.append(image, caption);
    dialog.append(frame, close);
    document.body.append(dialog);

    close.addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog || event.target === frame) dialog.close();
    });
    dialog.addEventListener("close", () => {
      document.body.classList.remove("is-lightbox-open");
      image.removeAttribute("src");
      image.alt = "";
      caption.textContent = "";
    });

    state.lightbox = dialog;
    return dialog;
  }

  function imageCaption(source) {
    const figureCaption = source.closest("figure")?.querySelector("figcaption");
    return figureCaption?.textContent?.trim() || source.alt?.trim() || "";
  }

  function openLightbox(source) {
    const dialog = ensureLightbox();
    const image = dialog.querySelector(".image-lightbox__image");
    const caption = dialog.querySelector(".image-lightbox__caption");

    image.src = source.currentSrc || source.src;
    image.alt = source.alt || "";
    caption.textContent = imageCaption(source);
    caption.hidden = !caption.textContent;
    document.body.classList.add("is-lightbox-open");
    dialog.showModal();
  }

  function isContentImage(image) {
    if (!image.matches(".md-content img")) return false;
    if (image.closest(".md-header, .md-footer, .md-nav, .md-logo, a.md-icon")) return false;
    return !image.matches(".twemoji, .emoji, [data-no-lightbox]");
  }

  function enhanceImages() {
    document.querySelectorAll(".md-content img").forEach((image) => {
      if (!isContentImage(image) || image.dataset.lightbox === "true") return;

      image.dataset.lightbox = "true";
      image.tabIndex = 0;
      image.setAttribute("role", "button");
      image.setAttribute("aria-label", `查看大图${image.alt ? `：${image.alt}` : ""}`);

      image.addEventListener("click", (event) => {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        openLightbox(image);
      });

      image.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        openLightbox(image);
      });
    });
  }

  function enhanceWideVisuals() {
    const svgImages = document.querySelectorAll(
      '.md-content img[src$=".svg"], .md-content img[src*=".svg?"]'
    );

    svgImages.forEach((image) => {
      if (image.parentElement?.classList.contains("md-visual-scroll")) return;
      const wrapper = document.createElement("div");
      wrapper.className = "md-visual-scroll";
      wrapper.tabIndex = 0;
      wrapper.setAttribute("role", "region");
      image.before(wrapper);
      wrapper.append(image);

      const classify = () => {
        const width = image.naturalWidth || 0;
        const height = image.naturalHeight || 1;
        const ratio = width / height;
        const isWide = ratio > 5.2 || (width > 1800 && ratio > 2.8);
        wrapper.classList.toggle("is-wide", isWide);
        wrapper.setAttribute(
          "aria-label",
          image.alt
            ? `${isWide ? "可横向滚动" : "可放大查看"}的图：${image.alt}`
            : isWide
              ? "可横向滚动的技术图"
              : "可放大查看的技术图"
        );
      };

      if (image.complete) classify();
      else image.addEventListener("load", classify, { once: true });
    });

    document.querySelectorAll(".md-typeset__table, .md-typeset pre, .md-visual-scroll").forEach((region) => {
      if (!region.hasAttribute("tabindex")) region.tabIndex = 0;
    });
  }

  function colorScheme() {
    return document.body?.getAttribute("data-md-color-scheme") ||
      document.documentElement.getAttribute("data-md-color-scheme") ||
      "default";
  }

  function markWideMermaid(container) {
    const svg = container.querySelector("svg");
    if (!svg) return;

    const viewBox = svg.viewBox?.baseVal;
    const width = viewBox?.width || Number.parseFloat(svg.getAttribute("width")) || 0;
    const height = viewBox?.height || Number.parseFloat(svg.getAttribute("height")) || 1;
    container.classList.toggle("is-wide", width > 960 || width / height > 2.6);
    container.tabIndex = 0;
    container.setAttribute("role", "region");
    container.setAttribute("aria-label", "可横向滚动的技术流程图");
  }

  function ensureMermaidRuntime() {
    if (window.mermaid) return Promise.resolve(true);
    if (state.mermaidRuntimePromise) return state.mermaidRuntimePromise;
    if (!siteScriptUrl) return Promise.resolve(false);

    state.mermaidRuntimePromise = new Promise((resolve) => {
      const script = document.createElement("script");
      script.src = new URL("mermaid.min.js", siteScriptUrl).href;
      script.async = true;
      script.addEventListener("load", () => resolve(Boolean(window.mermaid)), { once: true });
      script.addEventListener("error", () => resolve(false), { once: true });
      document.head.append(script);
    });
    return state.mermaidRuntimePromise;
  }

  async function runMermaid() {
    const diagrams = Array.from(document.querySelectorAll(".md-content .mermaid-source"));
    if (!diagrams.length) return;
    for (const diagram of diagrams) {
      if (!diagram.dataset.mermaidSource) {
        diagram.dataset.mermaidSource = diagram.textContent.trim();
      }
    }
    if (!window.mermaid && !(await ensureMermaidRuntime())) return;

    const theme = colorScheme() === "slate" ? "dark" : "neutral";
    window.mermaid.initialize({
      startOnLoad: false,
      theme,
      securityLevel: "strict",
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif',
    });

    for (const diagram of diagrams) {
      const source = diagram.dataset.mermaidSource;
      diagram.classList.remove("is-wide");
      diagram.removeAttribute("data-processed");
      diagram.textContent = source;

      try {
        await window.mermaid.run({ nodes: [diagram], suppressErrors: true });
        markWideMermaid(diagram);
      } catch (_error) {
        diagram.removeAttribute("data-processed");
        diagram.textContent = source;
      }
    }
  }

  function renderMermaid() {
    state.mermaidQueue = state.mermaidQueue.then(runMermaid, runMermaid);
  }

  function observeColorScheme() {
    if (state.observedScheme !== null) return;
    state.observedScheme = colorScheme();

    const observer = new MutationObserver(() => {
      const nextScheme = colorScheme();
      if (nextScheme === state.observedScheme) return;
      state.observedScheme = nextScheme;
      renderMermaid();
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-md-color-scheme"],
    });
    if (document.body) {
      observer.observe(document.body, {
        attributes: true,
        attributeFilter: ["data-md-color-scheme"],
      });
    }
  }

  function initializePage() {
    state.article = document.querySelector(".md-content article, .md-content .md-typeset");
    ensureProgressBar();
    enhanceWideVisuals();
    enhanceImages();
    observeColorScheme();
    renderMermaid();
    requestProgressUpdate();
  }

  window.addEventListener("scroll", requestProgressUpdate, { passive: true });
  window.addEventListener("resize", requestProgressUpdate, { passive: true });
  window.addEventListener("load", () => {
    if (document.querySelector(".md-content .mermaid-source")) renderMermaid();
  }, { once: true });

  if (typeof document$ !== "undefined") {
    document$.subscribe(initializePage);
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializePage, { once: true });
  } else {
    initializePage();
  }
})();
