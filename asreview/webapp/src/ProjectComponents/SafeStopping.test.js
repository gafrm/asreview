import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "react-query";
import { ProjectAPI } from "api";
import SafeStopping, { SafeSetup } from "./SafeStopping";

jest.mock("api", () => ({
  ProjectAPI: {
    fetchStopping: jest.fn(),
    fetchPriorSearch: jest.fn(),
    configureSafe: jest.fn(),
    transitionSafe: jest.fn(),
  },
}));

let container, root, client;
const status = (overrides = {}) => ({
  id: "safe",
  phase: "primary",
  model: "elas_u4",
  ready: true,
  paused: false,
  stop: false,
  screened: 300,
  total: 1000,
  sample_count: 200,
  sample_target: 200,
  sample_relevant: 10,
  estimated_relevant: 50,
  value: 100,
  checks: [
    {
      id: "keys",
      label: "Key studies marked relevant",
      value: 0,
      target: 1,
      met: false,
    },
    {
      id: "streak",
      label: "Consecutive exclusions in this phase",
      value: 100,
      target: 100,
      met: true,
    },
  ],
  ...overrides,
});

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  jest.clearAllMocks();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  client = new QueryClient({
    defaultOptions: { queries: { retry: false, cacheTime: 0 } },
  });
  ProjectAPI.fetchStopping.mockResolvedValue(status());
  ProjectAPI.fetchPriorSearch.mockResolvedValue({ result: [] });
});

afterEach(async () => {
  await act(async () => root.unmount());
  client.clear();
  container.remove();
});

const render = async (element) => {
  await act(async () => {
    root.render(
      <QueryClientProvider client={client}>{element}</QueryClientProvider>,
    );
  });
};
const button = (text) =>
  [...container.querySelectorAll("button")].find((node) =>
    node.textContent.includes(text),
  );

test("100 exclusions alone does not offer a phase transition", async () => {
  await render(<SafeStopping project_id="test" status={status()} />);
  expect(container.textContent).toContain(
    "Pending: Key studies marked relevant",
  );
  expect(button("Start ELAS l2")).toBeUndefined();
});

test("compact screening keeps all four condition statuses visible", async () => {
  const checks = [
    {
      id: "keys",
      label: "Key studies marked relevant",
      value: 1,
      target: 2,
      met: false,
    },
    {
      id: "estimate",
      label: "Twice the estimate",
      value: 400,
      target: 300,
      met: true,
    },
    {
      id: "fraction",
      label: "Ten percent",
      value: 400,
      target: 1234,
      met: false,
    },
    {
      id: "streak",
      label: "Consecutive exclusions",
      value: 73,
      target: 100,
      met: false,
    },
  ];
  await render(
    <SafeStopping project_id="test" status={status({ checks })} compact />,
  );
  const tracker = container.querySelector(
    '[aria-label="Stopping conditions tracker"]',
  );
  expect(tracker.querySelectorAll(".MuiChip-root")).toHaveLength(4);
  expect(tracker.textContent).toContain("Pending: Key studies 1/2");
  expect(tracker.textContent).toContain("Met: Screened: 2× estimate 400/300");
  expect(tracker.textContent).toContain("Pending: Screened: 10% 400/1234");
  expect(tracker.textContent).toContain(
    "Pending: Consecutive exclusions 73/100",
  );
  expect(button("Show criteria")).toBeDefined();
});

test("primary pause offers the second model and never an ignore-stop button", async () => {
  const paused = status({ stop: true, paused: true });
  ProjectAPI.transitionSafe.mockResolvedValue(
    status({ phase: "secondary", ready: false, value: 0 }),
  );
  await render(<SafeStopping project_id="test" status={paused} />);
  expect(container.textContent).toContain("Screening paused");
  expect(button("Review more")).toBeUndefined();
  await act(async () => button("Start ELAS l2").click());
  expect(ProjectAPI.transitionSafe).toHaveBeenCalledWith({
    project_id: "test",
    action: "secondary",
  });
});

test("training screen provides retry and no random-ranking bypass", async () => {
  await render(
    <SafeStopping
      project_id="test"
      status={status({ ready: false })}
      trainingError={{ message: "Model download failed" }}
    />,
  );
  expect(container.textContent).toContain("Model download failed");
  expect(button("Retry model training")).toBeDefined();
  expect(button("I can't wait")).toBeUndefined();
});

test("secondary stop explicitly leaves independent quality control outstanding", async () => {
  await render(
    <SafeStopping
      project_id="test"
      status={status({ phase: "secondary", stop: true, paused: true })}
    />,
  );
  expect(container.textContent).toContain("independent quality-control review");
  expect(button("Start ELAS l2")).toBeUndefined();
});

test("setup requires explicit key-study selection or an explicit empty list", async () => {
  ProjectAPI.configureSafe.mockResolvedValue(status({ phase: "random" }));
  const started = jest.fn();
  await render(<SafeSetup project_id="test" onStarted={started} />);
  expect(button("Start SAFE screening").disabled).toBe(true);
  await act(async () =>
    container.querySelector('input[type="checkbox"]').click(),
  );
  expect(button("Start SAFE screening").disabled).toBe(false);
  await act(async () => button("Start SAFE screening").click());
  expect(ProjectAPI.configureSafe).toHaveBeenCalledWith({
    project_id: "test",
    key_record_ids: [],
    no_key_studies: true,
  });
  expect(started).toHaveBeenCalledTimes(1);
});
