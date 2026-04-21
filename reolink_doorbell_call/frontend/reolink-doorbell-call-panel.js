const PANEL_FALLBACK_PATH = "/";
const DEVICE_HOME_INTENT_URI =
  "intent:#Intent;action=android.intent.action.MAIN;category=android.intent.category.HOME;launchFlags=0x10000000;end";

const getPlatformKind = () => {
  const userAgent = String(window.navigator?.userAgent || "");
  if (/android/i.test(userAgent)) {
    return "android";
  }
  if (
    /iphone|ipad|ipod/i.test(userAgent) ||
    (/macintosh/i.test(userAgent) && Number(window.navigator?.maxTouchPoints || 0) > 1)
  ) {
    return "ios";
  }
  return "other";
};

const navigateWithinHa = (path) => {
  window.history.pushState(null, "", path);
  window.dispatchEvent(new Event("location-changed"));
};

const exitToHaHome = () => {
  navigateWithinHa(PANEL_FALLBACK_PATH);
};

const exitToDeviceHome = () => {
  if (getPlatformKind() === "android") {
    window.setTimeout(() => {
      exitToHaHome();
    }, 900);
    try {
      window.location.assign(DEVICE_HOME_INTENT_URI);
    } catch (error) {
      console.warn("exitToDeviceHome failed", error);
      exitToHaHome();
    }
    return;
  }
  if (typeof window.close === "function") {
    window.close();
  }
  window.setTimeout(() => {
    exitToHaHome();
  }, 150);
};

const createPanelCardElement = async (config) => {
  if (window.loadCardHelpers) {
    const helpers = await window.loadCardHelpers();
    return helpers.createCardElement(config);
  }
  await customElements.whenDefined("hui-picture-entity-card");
  const element = document.createElement("hui-picture-entity-card");
  element.setConfig(config);
  return element;
};

class ReolinkDoorbellCallPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = undefined;
    this._panel = undefined;
    this._route = undefined;
    this._card = undefined;
    this._cardSignature = "";

    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          min-height: 100vh;
          background: #04070d;
          color: #f5f7fb;
        }
        .page {
          box-sizing: border-box;
          min-height: 100vh;
          margin: 0 auto;
          padding:
            max(12px, env(safe-area-inset-top))
            0
            max(24px, env(safe-area-inset-bottom))
            0;
          display: flex;
          justify-content: center;
        }
        .shell {
          position: relative;
          width: 100%;
          max-width: 430px;
          min-height: calc(100vh - max(12px, env(safe-area-inset-top)) - max(24px, env(safe-area-inset-bottom)));
          margin: 0 auto;
          background:
            linear-gradient(180deg, rgba(7, 12, 21, 0.1), rgba(7, 12, 21, 0.66)),
            #000;
          overflow: hidden;
        }
        .stage {
          position: absolute;
          inset: 0;
        }
        .stage > * {
          display: block;
          width: 100%;
          height: 100%;
        }
        .actions {
          position: absolute;
          left: 50%;
          right: auto;
          bottom: max(18px, env(safe-area-inset-bottom));
          transform: translateX(-50%);
          z-index: 2;
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 10px;
          width: calc(100% - 28px);
          max-width: 328px;
        }
        .actions::before {
          content: "";
          position: absolute;
          inset: -14px -10px;
          border-radius: 24px;
          background: linear-gradient(180deg, rgba(2, 6, 14, 0.08), rgba(2, 6, 14, 0.72));
          backdrop-filter: blur(10px);
          z-index: -1;
        }
        button {
          border: 0;
          border-radius: 18px;
          min-height: 54px;
          padding: 10px 12px;
          background: rgba(255, 255, 255, 0.14);
          color: #f5f7fb;
          cursor: pointer;
          font: inherit;
          font-size: 0.95rem;
          backdrop-filter: blur(6px);
        }
        button.primary {
          background: rgba(231, 60, 72, 0.92);
        }
        .message {
          position: absolute;
          left: 16px;
          right: 16px;
          top: 50%;
          transform: translateY(-50%);
          z-index: 3;
          padding: 18px;
          border-radius: 20px;
          background: rgba(7, 12, 21, 0.82);
          color: rgba(245, 247, 251, 0.84);
          line-height: 1.6;
          text-align: center;
        }
        @media (max-width: 720px) {
          .page {
            padding:
              max(8px, env(safe-area-inset-top))
              0
              max(18px, env(safe-area-inset-bottom))
              0;
          }
          .shell {
            max-width: none;
            min-height: calc(100vh - max(8px, env(safe-area-inset-top)) - max(18px, env(safe-area-inset-bottom)));
          }
          .actions {
            width: calc(100% - 20px);
          }
          button {
            min-height: 50px;
            font-size: 0.88rem;
          }
        }
      </style>
      <div class="page">
        <div class="shell">
          <div class="stage"></div>
          <div class="actions">
            <button type="button" data-action="exit">退出首页</button>
            <button class="primary" type="button" data-action="hangup">挂断回桌面</button>
          </div>
          <div class="message" hidden></div>
        </div>
      </div>
    `;

    this._stage = this.shadowRoot.querySelector(".stage");
    this._message = this.shadowRoot.querySelector(".message");
    this._hangupButton = this.shadowRoot.querySelector('button[data-action="hangup"]');
    this._syncPlatformUi();
    this.shadowRoot.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button) {
        return;
      }
      if (button.dataset.action === "exit") {
        exitToHaHome();
        return;
      }
      if (button.dataset.action === "hangup") {
        void this._handleHangup();
        return;
      }
    });
  }

  set hass(hass) {
    this._hass = hass;
    if (this._card) {
      this._card.hass = hass;
    }
    void this._renderPanel();
  }

  set panel(panel) {
    this._panel = panel;
    void this._renderPanel();
  }

  set route(route) {
    this._route = route;
    void this._renderPanel();
  }

  connectedCallback() {
    this._syncPlatformUi();
    void this._renderPanel();
  }

  _getSearchParams() {
    return new URL(window.location.href).searchParams;
  }

  _getCameraEntityId() {
    const params = this._getSearchParams();
    return String(params.get("camera_entity_id") || "").trim();
  }

  _getEntryId() {
    const params = this._getSearchParams();
    return String(params.get("entry_id") || "").trim();
  }

  _syncPlatformUi() {
    if (!this._hangupButton) {
      return;
    }
    const platform = getPlatformKind();
    if (platform === "android") {
      this._hangupButton.textContent = "挂断回桌面";
      return;
    }
    if (platform === "ios") {
      this._hangupButton.textContent = "挂断返回";
      return;
    }
    this._hangupButton.textContent = "挂断";
  }

  async _handleHangup() {
    const entryId = this._getEntryId();
    if (this._hass && entryId) {
      try {
        await this._hass.callService("reolink_doorbell_call", "clear_notification", {
          entry_id: entryId,
        });
      } catch (error) {
        console.warn("clear_notification failed", error);
      }
    }
    if (getPlatformKind() === "android") {
      exitToDeviceHome();
      return;
    }
    exitToHaHome();
  }

  async _renderPanel() {
    if (!this._hass) {
      return;
    }

    const entityId = this._getCameraEntityId();
    if (!entityId) {
      this._stage.innerHTML = "";
      this._message.hidden = false;
      this._message.textContent =
        "当前没有传入摄像头实体。请从门铃通知的“接听”按钮进入，或从主页卡片点开。";
      return;
    }

    const stateObj = this._hass.states[entityId];
    if (!stateObj) {
      this._stage.innerHTML = "";
      this._message.hidden = false;
      this._message.textContent = `找不到实体 ${entityId}`;
      return;
    }

    this._message.hidden = true;

    const pictureConfig = {
      type: "picture-entity",
      entity: entityId,
      camera_view: "live",
      show_state: false,
      show_name: false,
      aspect_ratio: "9:16",
      tap_action: {
        action: "none",
      },
      hold_action: {
        action: "none",
      },
    };
    const signature = JSON.stringify(pictureConfig);
    if (signature === this._cardSignature && this._card) {
      this._card.hass = this._hass;
      return;
    }

    const card = await createPanelCardElement(pictureConfig);
    card.hass = this._hass;
    card.style.setProperty("--ha-card-background", "transparent");
    card.style.setProperty("--ha-card-border-width", "0");
    card.style.setProperty("--ha-card-border-radius", "0");
    card.style.setProperty("--ha-card-box-shadow", "none");
    if (this._card) {
      this._stage.replaceChild(card, this._card);
    } else {
      this._stage.appendChild(card);
    }
    this._card = card;
    this._cardSignature = signature;
  }
}

customElements.define("reolink-doorbell-call-panel", ReolinkDoorbellCallPanel);
