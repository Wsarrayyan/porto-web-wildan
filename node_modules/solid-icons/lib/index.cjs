'use strict';

var web = require('solid-js/web');
var solidJs = require('solid-js');

const CustomIcon = props => IconTemplate(props.src, props);
function IconTemplate(iconSrc, props) {
  const mergedProps = web.mergeProps(iconSrc.a, props);
  const [_, svgProps] = solidJs.splitProps(mergedProps, ["src"]);
  const [content, setContent] = solidJs.createSignal("");
  const rawContent = solidJs.createMemo(() => props.title ? `${iconSrc.c}<title>${props.title}</title>` : iconSrc.c);
  solidJs.createEffect(() => setContent(rawContent()));
  solidJs.onCleanup(() => {
    setContent("");
  });
  return web.ssrElement("svg", () => ({
    "stroke": iconSrc.a?.stroke,
    "color": props.color || "currentColor",
    "fill": props.color || "currentColor",
    "stroke-width": "0",
    "style": {
      ...props.style,
      overflow: "visible"
    },
    ...svgProps,
    "height": props.size || "1em",
    "width": props.size || "1em",
    "xmlns": "http://www.w3.org/2000/svg",
    "innerHTML": content()
  }), () => web.isServer && web.escape(web.ssr(rawContent())), true);
}

exports.CustomIcon = CustomIcon;
exports.IconTemplate = IconTemplate;
