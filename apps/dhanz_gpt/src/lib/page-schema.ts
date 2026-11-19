import StarterKit from "@tiptap/starter-kit";

/**
 * The page editor's content model, shared by the browser editor and the server (draft conversion).
 * Only these nodes and marks exist; anything else in pasted or generated HTML is dropped.
 */
export const pageExtensions = [
  StarterKit.configure({
    heading: { levels: [1, 2, 3] },
    link: {
      openOnClick: false,
      autolink: true,
      protocols: ["http", "https", "mailto"],
      isAllowedUri: (url) => /^(https?:|mailto:)/i.test(url),
      HTMLAttributes: { rel: "noopener noreferrer nofollow", target: "_blank" },
    },
  }),
];
