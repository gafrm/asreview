import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "react-query";
import { ProjectAPI } from "api";
import { projectModes } from "globals.js";
import SetupDialog from "./SetupDialog";

jest.mock("react-router-dom", () => ({
  useNavigate: () => jest.fn(),
}), { virtual: true });

jest.mock("api", () => ({
  ProjectAPI: {
    fetchInfo: jest.fn(),
    mutateInfo: jest.fn(),
    mutateReviewStatus: jest.fn(),
  },
}));
jest.mock("ProjectComponents/SetupComponents", () => ({
  DatasetCard: () => null,
  ModelCard: () => null,
  PriorCard: () => null,
  TagCard: () => null,
}));
jest.mock("../SafeStopping", () => ({
  SafeSetup: () => <button>Start SAFE screening</button>,
}));

test("SAFE is the default and only the selected procedure can be started", async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, cacheTime: 0 } },
  });
  ProjectAPI.fetchInfo.mockResolvedValue({ id: "test", name: "Test" });
  ProjectAPI.mutateReviewStatus.mockResolvedValue({ status: "review" });
  const button = (label) =>
    [...document.querySelectorAll("button")].find((node) => node.textContent === label);
  try {
    await act(async () => {
      root.render(
        <QueryClientProvider client={client}>
            <SetupDialog project_id="test" mode={projectModes.ORACLE} open onClose={() => {}} />
        </QueryClientProvider>,
      );
    });
    expect(button("Start SAFE screening")).toBeDefined();
    expect(button("Start standard screening")).toBeUndefined();
    expect(button("Screen")).toBeUndefined();
    await act(async () => document.querySelector('input[value="standard"]').click());
    expect(button("Start SAFE screening")).toBeUndefined();
    expect(button("Start standard screening")).toBeDefined();
    expect(document.body.textContent).toContain("Standard screening is not SAFE");
    await act(async () => document.querySelector('input[value="safe"]').click());
    expect(button("Start SAFE screening")).toBeDefined();
    expect(button("Start standard screening")).toBeUndefined();
    expect(ProjectAPI.mutateReviewStatus).not.toHaveBeenCalled();
  } finally {
    await act(async () => root.unmount());
    client.clear();
    host.remove();
  }
});
