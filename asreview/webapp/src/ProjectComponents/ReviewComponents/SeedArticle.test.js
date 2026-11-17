import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "react-query";
import { createTheme, ThemeProvider } from "@mui/material/styles";
import { ProjectAPI } from "api";
import RecordCard from "./RecordCard";
import RecordCardLabeler from "./RecordCardLabeler";

jest.mock("api", () => ({ ProjectAPI: { mutateClassification: jest.fn() } }));
jest.mock("./index", () => ({
  RecordCardModelTraining: () => null,
  RecordCardLabeler: () => null,
}));

let container, root, client;
const theme = createTheme({ palette: { tertiary: { main: "#226655" } } });

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  jest.clearAllMocks();
  ProjectAPI.mutateClassification.mockResolvedValue({ success: true });
  client = new QueryClient({
    defaultOptions: { queries: { retry: false, cacheTime: 0 } },
  });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  client.clear();
  container.remove();
});

const render = async (element) => {
  await act(async () =>
    root.render(
      <QueryClientProvider client={client}>
        <ThemeProvider theme={theme}>{element}</ThemeProvider>
      </QueryClientProvider>,
    ),
  );
};
const button = (text) =>
  [...document.querySelectorAll("button")].find(
    (node) => node.textContent.trim() === text,
  );
const labeler = (overrides = {}) => (
  <RecordCardLabeler
    project_id="test"
    record_id={7}
    label={null}
    tagsForm={[]}
    tagValues={[]}
    hotkeys
    isKeyStudy
    {...overrides}
  />
);
const press = async (key, code) => {
  await act(async () => {
    document.body.dispatchEvent(
      new KeyboardEvent("keydown", { key, code, bubbles: true }),
    );
    document.body.dispatchEvent(
      new KeyboardEvent("keyup", { key, code, bubbles: true }),
    );
  });
};

test("seed articles have a prominent text label and distinct border", async () => {
  await render(
    <RecordCard
      project_id="test"
      transitionType={null}
      record={{
        record_id: 7,
        title: "Known key study",
        abstract: "Example",
        is_key_study: true,
      }}
    />,
  );
  expect(container.textContent).toContain(
    "Predefined key study (seed article)",
  );
  const card = container.querySelector('[aria-label="Seed article"]');
  expect(getComputedStyle(card).borderTopWidth).toBe("3px");
});

test("excluding a seed article needs confirmation, and cancel saves nothing", async () => {
  await render(labeler());
  await act(async () => button("Not relevant").click());
  expect(document.querySelector('[role="dialog"]').textContent).toContain(
    "Exclude this seed article?",
  );
  expect(ProjectAPI.mutateClassification).not.toHaveBeenCalled();
  await act(async () => button("Go back").click());
  expect(ProjectAPI.mutateClassification).not.toHaveBeenCalled();
  await act(async () => button("Not relevant").click());
  await act(async () => button("Confirm exclusion").click());
  expect(ProjectAPI.mutateClassification).toHaveBeenCalledWith(
    expect.objectContaining({
      record_id: 7,
      label: 0,
      confirm_key_exclusion: true,
      post: true,
    }),
  );
});

test("keyboard exclusion opens the same confirmation and cannot bypass it", async () => {
  await render(labeler());
  await press("i", "KeyI");
  expect(document.querySelector('[role="dialog"]').textContent).toContain(
    "Exclude this seed article?",
  );
  await press("i", "KeyI");
  await press("r", "KeyR");
  expect(ProjectAPI.mutateClassification).not.toHaveBeenCalled();
  await act(async () => button("Confirm exclusion").click());
  expect(ProjectAPI.mutateClassification).toHaveBeenCalledTimes(1);
});

test("including a seed article remains a single human decision", async () => {
  await render(labeler());
  await act(async () => button("Relevant").click());
  expect(ProjectAPI.mutateClassification).toHaveBeenCalledWith(
    expect.objectContaining({
      label: 1,
      confirm_key_exclusion: false,
    }),
  );
});

test("ordinary articles retain one-click exclusion", async () => {
  await render(labeler({ isKeyStudy: false }));
  await act(async () => button("Not relevant").click());
  expect(ProjectAPI.mutateClassification).toHaveBeenCalledWith(
    expect.objectContaining({
      label: 0,
      confirm_key_exclusion: false,
    }),
  );
  expect(document.querySelector('[role="dialog"]')).toBeNull();
});

test("changing a relevant seed to excluded in history also asks for confirmation", async () => {
  await render(labeler({ label: 1 }));
  await act(async () =>
    container.querySelector('[id="card-positioned-button"]').click(),
  );
  const change = [...document.querySelectorAll('[role="menuitem"]')].find(
    (node) => node.textContent.includes("Change to Not Relevant"),
  );
  await act(async () => change.click());
  expect(ProjectAPI.mutateClassification).not.toHaveBeenCalled();
  await act(async () => button("Confirm exclusion").click());
  expect(ProjectAPI.mutateClassification).toHaveBeenCalledWith(
    expect.objectContaining({
      label: 0,
      confirm_key_exclusion: true,
      post: false,
    }),
  );
});
