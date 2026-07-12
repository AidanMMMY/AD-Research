import stylelint from "stylelint";

const ruleName = "ad-research/no-bare-color-values";

const messages = stylelint.utils.ruleMessages(ruleName, {
  rejected: (color) =>
    `Bare color value ${color} is not allowed; use a design token instead.`,
});

const HEX_COLOR = /#([0-9A-Fa-f]{3,4}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})\b/g;
const RGB_COLOR = /rgba?\(\s*[^)]+\s*\)/gi;

const meta = {
  url: undefined,
  fixable: false,
};

/** @type {import('stylelint').Rule} */
const rule = (primaryOption) => {
  return (root, result) => {
    if (!primaryOption) return;

    const filePath = root.source?.input?.file;
    if (filePath && filePath.endsWith("src/styles/theme.css")) {
      return;
    }

    root.walkDecls((decl) => {
      const prop = decl.prop.toLowerCase();
      if (prop === "mask-image" || prop === "-webkit-mask-image") {
        return;
      }

      let parent = decl.parent;
      while (parent) {
        if (
          parent.type === "atrule" &&
          parent.name.toLowerCase() === "keyframes"
        ) {
          return;
        }
        parent = parent.parent;
      }

      const value = decl.value;
      const hexMatches = value.match(HEX_COLOR) || [];
      const rgbMatches = value.match(RGB_COLOR) || [];

      [...hexMatches, ...rgbMatches].forEach((color) => {
        stylelint.utils.report({
          message: messages.rejected(color),
          node: decl,
          result,
          ruleName,
        });
      });
    });
  };
};

rule.messages = messages;
rule.meta = meta;

export default { ruleName, rule };
