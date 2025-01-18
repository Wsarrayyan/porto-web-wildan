import { mergeProps, getNextElement, spread, insert, isServer, ssr, runHydrationEvents, template } from 'solid-js/web';
import { splitProps, createSignal, createMemo, createEffect, onCleanup } from 'solid-js';

const _tmpl$ = /*#__PURE__*/template(`<svg stroke-width="0"></svg>`, 2);
const CustomIcon = props => IconTemplate(props.src, props);
function IconTemplate(iconSrc, props) {
  const mergedProps = mergeProps(iconSrc.a, props);
  const [_, svgProps] = splitProps(mergedProps, ["src"]);
  const [content, setContent] = createSignal("");
  const rawContent = createMemo(() => props.title ? `${iconSrc.c}<title>${props.title}</title>` : iconSrc.c);
  createEffect(() => setContent(rawContent()));
  onCleanup(() => {
    setContent("");
  });
  return (() => {
    const _el$ = getNextElement(_tmpl$);
    spread(_el$, mergeProps({
      get stroke() {
        return iconSrc.a?.stroke;
      },
      get color() {
        return props.color || "currentColor";
      },
      get fill() {
        return props.color || "currentColor";
      },
      get style() {
        return {
          ...props.style,
          overflow: "visible"
        };
      }
    }, svgProps, {
      get height() {
        return props.size || "1em";
      },
      get width() {
        return props.size || "1em";
      },
      "xmlns": "http://www.w3.org/2000/svg",
      get innerHTML() {
        return content();
      }
    }), true, true);
    insert(_el$, () => isServer && ssr(rawContent()));
    runHydrationEvents();
    return _el$;
  })();
}

export { CustomIcon, IconTemplate };
