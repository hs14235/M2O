import React from "react";
import ReactDOM from "react-dom/client";
import StyleGuide from "./StyleGuide";
import "../theme.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <StyleGuide />
  </React.StrictMode>,
);
