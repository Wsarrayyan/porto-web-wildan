import { createEffect, createMemo, createSignal, onCleanup, splitProps, } from "solid-js";
import { isServer, mergeProps, ssr } from "solid-js/web";
export const CustomIcon = (props) => IconTemplate(props.src, props);
export function IconTemplate(iconSrc, props) {
    const mergedProps = mergeProps(iconSrc.a, props);
    const [_, svgProps] = splitProps(mergedProps, ["src"]);
    const [content, setContent] = createSignal("");
    const rawContent = createMemo(() => props.title ? `${iconSrc.c}<title>${props.title}</title>` : iconSrc.c);
    createEffect(() => setContent(rawContent()));
    onCleanup(() => {
        setContent("");
    });
    return (<svg stroke={iconSrc.a?.stroke} color={props.color || "currentColor"} fill={props.color || "currentColor"} stroke-width="0" style={{
            ...props.style,
            overflow: "visible",
        }} {...svgProps} height={props.size || "1em"} width={props.size || "1em"} xmlns="http://www.w3.org/2000/svg" innerHTML={content()}>
      {isServer && ssr(rawContent())}
    </svg>);
}
