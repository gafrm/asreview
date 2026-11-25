import axios from "axios";
import ProjectAPI from "./ProjectAPI";

jest.mock("axios");
jest.mock("globals.js", () => ({ api_url: "/api/" }));
jest.mock("./axiosErrorHandler", () => ({
  axiosErrorHandler: (error) => error,
}));

beforeEach(() => {
  jest.clearAllMocks();
  axios.mockResolvedValue({ data: { id: "test" } });
});

test.each([true, false])(
  "dataset creation transmits automatic deduplication = %s",
  async (automaticDeduplication) => {
    const file = new File(["title\nExample"], "dataset.csv", {
      type: "text/csv",
    });
    await expect(
      ProjectAPI.createProject({ mode: "oracle", file, automaticDeduplication }),
    ).resolves.toEqual({ id: "test" });
    expect(axios).toHaveBeenCalledTimes(1);
    const request = axios.mock.calls[0][0];
    expect(request.url).toBe("/api/projects/create");
    expect(request.method).toBe("post");
    expect(request.data.get("mode")).toBe("oracle");
    expect(request.data.get("automatic_deduplication")).toBe(
      String(automaticDeduplication),
    );
    expect(request.data.get("file").name).toBe("dataset.csv");
  },
);

test("omitted policy preserves the server default", async () => {
  await ProjectAPI.createProject({ mode: "oracle", url: "https://example.org/data.ris" });
  const request = axios.mock.calls[0][0];
  expect(request.data.has("automatic_deduplication")).toBe(false);
});
