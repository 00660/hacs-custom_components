const DEFAULT_PANEL_PATH = "/reolink-doorbell-call";

const pickCameraEntity = (config) =>
  String(config.entity || config.camera_entity_id || "").trim();

const fireMoreInfo = (target, entityId) => {
  target.dispatchEvent(
    new CustomEvent("hass-more-info", {
      bubbles: true,
      composed: true,
      detail: { entityId },
    }),
  );
};

const navigateTo = (path) => {
  window.history.pushState(null, "", path);
  window.dispatchEvent(new Event("location-changed"));
};

const buildPanelPath = (config) => {
  const entityId = pickCameraEntity(config);
  const basePath = String(config.panel_path || DEFAULT_PANEL_PATH).trim() || DEFAULT_PANEL_PATH;
  const params = new URLSearchParams();
  if (entityId) {
    params.set("camera_entity_id", entityId);
  }
  if (config.title) {
    params.set("title", String(config.title));
  }
  const query = params.toString();
  return query ? `${basePath}?${query}` : basePath;
};

const buildPictureEntityConfig = (config) => ({
  type: "picture-entity",
  entity: pickCameraEntity(config),
  camera_view: "live",
  show_state: false,
  show_name: Boolean(config.show_name),
  name: config.title || undefined,
  aspect_ratio: config.aspect_ratio || "16:9",
  tap_action: {
    action: "navigate",
    navigation_path: buildPanelPath(config),
  },
  hold_action: {
    action: "more-info",
  },
});

const createCardElement = async (config) => {
  if (window.loadCardHelpers) {
    const helpers = await window.loadCardHelpers();
    return helpers.createCardElement(config);
  }
  await customElements.whenDefined("hui-picture-entity-card");
  const element = document.createElement("hui-picture-entity-card");
  element.setConfig(config);
  return element;
};

class ReolinkDoorbellCallCard extends HTMLElement {
  static getStubConfig(_hass, entities) {
    const firstCamera = (entities || []).find((entityId) => entityId.startsWith("camera."));
    return {
      type: "custom:reolink-doorbell-call-card",
      entity: firstCamera || "",
      show_name: false,
    };
  }

  static getConfigForm() {
    return {
      schema: [
        {
          name: "entity",
          required: true,
          selector: { entity: {} },
        },
        {
          name: "title",
          selector: { text: {} },
        },
        {
          name: "panel_path",
          selector: { text: {} },
        },
        {
          name: "show_name",
          selector: { boolean: {} },
        },
      ],
      computeLabel: (schema) => {
        switch (schema.name) {
          case "entity":
            return "摄像头实体";
          case "title":
            return "卡片标题";
          case "panel_path":
            return "大屏路径";
          case "show_name":
            return "显示标题";
          default:
            return schema.name;
        }
      },
    };
  }

  constructor() {
    super();
    this._config = undefined;
    this._hass = undefined;
    this._card = undefined;
    this._cardSignature = "";

    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }
        .shell {
          display: grid;
          gap: 12px;
        }
        .toolbar {
          display: flex;
          gap: 8px;
          justify-content: flex-end;
          flex-wrap: wrap;
        }
        button {
          border: 0;
          border-radius: 999px;
          padding: 8px 14px;
          background: rgba(27, 32, 48, 0.08);
          color: var(--primary-text-color);
          cursor: pointer;
          font: inherit;
        }
        button.primary {
          background: var(--primary-color);
          color: var(--text-primary-color, #fff);
        }
        .message {
          color: var(--secondary-text-color);
          font-size: 0.95rem;
          line-height: 1.5;
        }
      </style>
      <div class="shell">
        <div class="frame"></div>
        <div class="toolbar">
          <button class="primary" type="button" data-action="open">打开大屏</button>
          <button type="button" data-action="more-info">实体详情</button>
        </div>
        <div class="message" hidden></div>
      </div>
    `;

    this._frame = this.shadowRoot.querySelector(".frame");
    this._message = this.shadowRoot.querySelector(".message");
    this.shadowRoot.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button || !this._config) {
        return;
      }
      const entityId = pickCameraEntity(this._config);
      if (!entityId) {
        return;
      }
      if (button.dataset.action === "open") {
        navigateTo(buildPanelPath(this._config));
        return;
      }
      if (button.dataset.action === "more-info") {
        fireMoreInfo(this, entityId);
      }
    });
  }

  setConfig(config) {
    const entityId = pickCameraEntity(config);
    if (!entityId) {
      throw new Error("需要配置 camera 实体");
    }
    if (!entityId.startsWith("camera.")) {
      throw new Error("只支持 camera 域实体");
    }
    this._config = {
      type: "custom:reolink-doorbell-call-card",
      entity: entityId,
      title: String(config.title || "").trim(),
      panel_path: String(config.panel_path || DEFAULT_PANEL_PATH).trim() || DEFAULT_PANEL_PATH,
      show_name: Boolean(config.show_name),
      aspect_ratio: String(config.aspect_ratio || "16:9").trim() || "16:9",
    };
    void this._renderCard();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._card) {
      this._card.hass = hass;
    }
    void this._renderCard();
  }

  getCardSize() {
    return 6;
  }

  getGridOptions() {
    return {
      columns: 12,
      rows: 6,
      min_rows: 4,
    };
  }

  async _renderCard() {
    if (!this._config || !this._hass) {
      return;
    }

    const entityId = pickCameraEntity(this._config);
    const stateObj = this._hass.states[entityId];
    if (!stateObj) {
      this._message.hidden = false;
      this._message.textContent = `找不到实体 ${entityId}`;
      return;
    }

    this._message.hidden = true;
    const pictureConfig = buildPictureEntityConfig({
      ...this._config,
      title: this._config.title || stateObj.attributes.friendly_name || "",
    });
    const signature = JSON.stringify(pictureConfig);
    if (signature === this._cardSignature && this._card) {
      this._card.hass = this._hass;
      return;
    }

    const card = await createCardElement(pictureConfig);
    card.hass = this._hass;
    if (this._card) {
      this._frame.replaceChild(card, this._card);
    } else {
      this._frame.appendChild(card);
    }
    this._card = card;
    this._cardSignature = signature;
  }
}

customElements.define("reolink-doorbell-call-card", ReolinkDoorbellCallCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "reolink-doorbell-call-card",
  name: "Reolink Doorbell Call",
  description: "门铃主页大屏卡片，点按直接进入插件自带接听页。",
});
