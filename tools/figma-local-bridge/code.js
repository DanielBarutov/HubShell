// This development plugin intentionally exposes a small, typed canvas command set.
// It never evaluates JavaScript received from the bridge and never uses Figma REST.

figma.showUI(__html__, {
  width: 420,
  height: 270,
  title: "HubShell Local Canvas Bridge",
  themeColors: true,
});

const MAX_OPERATIONS = 40;
const MAX_TEXT_LENGTH = 2_000;
const MAX_NODE_SIZE = 10_000;
const FONT_FAMILIES = new Set(["Inter", "Noto Sans", "Roboto"]);

figma.ui.onmessage = async (message) => {
  if (message?.type !== "plugin-request" || typeof message.requestId !== "string") {
    return;
  }

  try {
    let result;
    if (message.command === "get_status") {
      result = getStatus();
    } else if (message.command === "apply_batch") {
      result = await applyBatch(message.arguments);
    } else {
      throw new Error("Unsupported bridge command");
    }
    respond(message.requestId, true, result);
  } catch (error) {
    respond(message.requestId, false, null, error instanceof Error ? error.message : "Unknown plugin error");
  }
};

function respond(requestId, ok, result, error) {
  figma.ui.postMessage({ type: "plugin-result", requestId, ok, result, error });
}

function getStatus() {
  return {
    page: { id: figma.currentPage.id, name: figma.currentPage.name },
    selection: figma.currentPage.selection.map((node) => ({ id: node.id, name: node.name, type: node.type })),
  };
}

async function applyBatch(input) {
  if (!input || !Array.isArray(input.operations) || input.operations.length === 0) {
    throw new Error("operations must be a non-empty array");
  }
  if (input.operations.length > MAX_OPERATIONS) {
    throw new Error(`At most ${MAX_OPERATIONS} operations are allowed per batch`);
  }

  const refs = new Map();
  const created = [];
  for (const operation of input.operations) {
    validateOperation(operation);
    const parent = await resolveParent(operation.parent, refs);
    const node = await createNode(operation);
    if (parent) {
      parent.appendChild(node);
    }
    if (operation.ref) {
      refs.set(operation.ref, node);
    }
    created.push(node);
  }

  if (input.selectCreated === true && created.length > 0) {
    figma.currentPage.selection = created;
    figma.viewport.scrollAndZoomIntoView(created);
  }
  return {
    created: created.map((node) => ({ id: node.id, name: node.name, type: node.type })),
  };
}

function validateOperation(operation) {
  if (!operation || typeof operation !== "object") {
    throw new Error("Every operation must be an object");
  }
  if (!new Set(["frame", "auto_layout", "rectangle", "ellipse", "text"]).has(operation.kind)) {
    throw new Error("Unsupported operation kind");
  }
  if (operation.ref !== undefined && (!/^[a-zA-Z][a-zA-Z0-9_-]{0,63}$/.test(operation.ref))) {
    throw new Error("ref must be a short identifier");
  }
  for (const field of ["x", "y", "width", "height", "cornerRadius", "gap", "padding"]) {
    if (operation[field] !== undefined && (!Number.isFinite(operation[field]) || Math.abs(operation[field]) > MAX_NODE_SIZE)) {
      throw new Error(`${field} must be a finite number within the allowed range`);
    }
  }
  if (operation.width !== undefined && operation.width <= 0) throw new Error("width must be positive");
  if (operation.height !== undefined && operation.height <= 0) throw new Error("height must be positive");
  if (operation.kind === "text") {
    if (typeof operation.characters !== "string" || operation.characters.length > MAX_TEXT_LENGTH) {
      throw new Error("text characters must be a string up to 2000 characters");
    }
    if (operation.fontFamily !== undefined && !FONT_FAMILIES.has(operation.fontFamily)) {
      throw new Error("fontFamily is not allowlisted");
    }
  }
  validatePaint(operation.fill, "fill");
  validatePaint(operation.stroke, "stroke");
}

function validatePaint(paint, field) {
  if (paint === undefined) return;
  if (!paint || typeof paint !== "object") throw new Error(`${field} must be a color object`);
  for (const channel of ["r", "g", "b"]) {
    if (!Number.isFinite(paint[channel]) || paint[channel] < 0 || paint[channel] > 1) {
      throw new Error(`${field}.${channel} must be a number from 0 to 1`);
    }
  }
  if (paint.opacity !== undefined && (!Number.isFinite(paint.opacity) || paint.opacity < 0 || paint.opacity > 1)) {
    throw new Error(`${field}.opacity must be a number from 0 to 1`);
  }
}

async function resolveParent(parentRef, refs) {
  if (parentRef === undefined || parentRef === null) return figma.currentPage;
  let parent = refs.get(parentRef);
  if (!parent) parent = await figma.getNodeByIdAsync(parentRef);
  if (!parent || !("appendChild" in parent)) {
    throw new Error("parent must identify a frame, section, component, instance, or page");
  }
  return parent;
}

async function createNode(operation) {
  let node;
  switch (operation.kind) {
    case "frame":
      node = figma.createFrame();
      break;
    case "auto_layout":
      node = figma.createFrame();
      node.layoutMode = operation.direction === "horizontal" ? "HORIZONTAL" : "VERTICAL";
      node.itemSpacing = operation.gap ?? 0;
      node.paddingTop = operation.padding ?? 0;
      node.paddingRight = operation.padding ?? 0;
      node.paddingBottom = operation.padding ?? 0;
      node.paddingLeft = operation.padding ?? 0;
      break;
    case "rectangle":
      node = figma.createRectangle();
      break;
    case "ellipse":
      node = figma.createEllipse();
      break;
    case "text":
      node = figma.createText();
      const fontName = { family: operation.fontFamily ?? "Inter", style: operation.fontStyle ?? "Regular" };
      await figma.loadFontAsync(fontName);
      node.fontName = fontName;
      node.fontSize = operation.fontSize ?? 16;
      node.characters = operation.characters;
      if (operation.textWidth !== undefined) {
        node.resize(operation.textWidth, node.height);
        node.textAutoResize = "HEIGHT";
      }
      break;
  }

  node.name = operation.name ?? operation.kind;
  if (operation.width !== undefined || operation.height !== undefined) {
    node.resize(operation.width ?? node.width, operation.height ?? node.height);
  }
  if (operation.x !== undefined) node.x = operation.x;
  if (operation.y !== undefined) node.y = operation.y;
  if (operation.cornerRadius !== undefined && "cornerRadius" in node) node.cornerRadius = operation.cornerRadius;
  if (operation.fill) node.fills = [toSolidPaint(operation.fill)];
  if (operation.stroke && "strokes" in node) {
    node.strokes = [toSolidPaint(operation.stroke)];
    node.strokeWeight = operation.strokeWeight ?? 1;
  }
  return node;
}

function toSolidPaint(color) {
  return {
    type: "SOLID",
    color: { r: color.r, g: color.g, b: color.b },
    opacity: color.opacity ?? 1,
  };
}
