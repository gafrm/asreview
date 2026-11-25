import React from "react";
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  FormControlLabel,
  LinearProgress,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "react-query";
import { ProjectAPI } from "api";
import CheckCircleOutline from "@mui/icons-material/CheckCircleOutline";
import RadioButtonUnchecked from "@mui/icons-material/RadioButtonUnchecked";
import SeedImport from "./SeedImport";

const phaseNames = {
  random: "Random sample",
  primary: "Primary screening · ELAS u4",
  secondary: "Second-model check · ELAS l2",
};

const criterionLabels = {
  keys: "Key studies",
  estimate: "Screened: 2× estimate",
  fraction: "Screened: 10%",
  streak: "Consecutive exclusions",
};

const defaultParameters = {
  sample_minimum: 200,
  sample_percent: 1,
  estimate_multiplier: 2,
  screened_percent: 10,
  primary_exclusions: 100,
  secondary_exclusions: 100,
};

const parameterFields = [
  ["sample_minimum", "Minimum random sample records"],
  ["sample_percent", "Random sample percentage"],
  ["estimate_multiplier", "Estimated relevant total multiplier"],
  ["screened_percent", "Minimum percentage screened"],
  ["primary_exclusions", "Primary consecutive exclusions"],
  ["secondary_exclusions", "Secondary consecutive exclusions"],
];

const validParameter = (key, value) =>
  Number.isSafeInteger(Number(value)) &&
  Number(value) >= 1 &&
  (!key.endsWith("_percent") || Number(value) <= 100);

const refreshQueries = (client, project_id) => {
  [
    "fetchStopping",
    "fetchRecord",
    "fetchProjectStatus",
    "fetchLearner",
    "fetchProject",
    "fetchProjects",
  ].forEach((name) => client.invalidateQueries([name]));
};

export const SafeSetup = ({ project_id, onStarted }) => {
  const client = useQueryClient();
  const [parameters, setParameters] = React.useState(defaultParameters);
  const validParameters = parameterFields.every(([key]) =>
    validParameter(key, parameters[key]),
  );
  const [keyword, setKeyword] = React.useState("");
  const [keys, setKeys] = React.useState([]);
  const [noKeys, setNoKeys] = React.useState(false);
  const [seedImport, setSeedImport] = React.useState(null);
  const [importBusy, setImportBusy] = React.useState(false);
  const importedKeys =
    seedImport?.rows.filter((row) => row.selected).map((row) => row.selected) ||
    [];
  const allKeys = Array.from(
    new Map(
      [...keys, ...importedKeys].map((record) => [record.record_id, record]),
    ).values(),
  );
  const unresolvedImport = seedImport?.rows.some(
    (row) => !row.selected && !row.not_present,
  );
  const { data: matches, isLoading } = useQuery(
    ["fetchPriorSearch", { project_id, keyword }],
    ProjectAPI.fetchPriorSearch,
    { enabled: keyword.length >= 2, refetchOnWindowFocus: false },
  );
  const configure = useMutation(ProjectAPI.configureSafe, {
    onSuccess: () => {
      refreshQueries(client, project_id);
      onStarted();
    },
  });
  return (
    <Card variant="outlined" sx={{ my: 3 }}>
      <CardContent>
        <Stack spacing={2}>
          <Typography variant="h6">SAFE automatic stopping</Typography>
          <Typography variant="body2">
            Configure the thresholds before screening. The random sample uses
            the larger of the minimum count and percentage (capped at the dataset
            size), and continues until both relevance classes are present.
            ELAS u4 requires all four primary criteria, including all selected
            key studies marked relevant. ELAS l2 uses a fresh exclusion counter.
            Parameters are locked when screening starts.
          </Typography>
          <Typography variant="body2">
            Enable this before adding prior knowledge or screening. Select the
            predefined key studies present in this dataset, using an imported
            list or the search field below; selecting a study does not label it.
            Duplicate groups count as one screening unit.
          </Typography>
          {parameterFields.map(([key, label]) => (
            <TextField
              key={key}
              label={label}
              type="number"
              value={parameters[key]}
              disabled={configure.isLoading}
              error={!validParameter(key, parameters[key])}
              inputProps={{
                min: 1,
                step: 1,
                ...(key.endsWith("_percent") ? { max: 100 } : {}),
              }}
              onChange={(event) =>
                setParameters((previous) => ({
                  ...previous,
                  [key]: event.target.value,
                }))
              }
            />
          ))}
          <Button
            disabled={configure.isLoading}
            onClick={() => setParameters(defaultParameters)}
          >
            Restore default thresholds
          </Button>
          <SeedImport
            project_id={project_id}
            value={seedImport}
            onChange={(report) => {
              setSeedImport(report);
              if (report) setNoKeys(false);
            }}
            onBusy={setImportBusy}
            disabled={configure.isLoading}
          />
          <Autocomplete
            multiple
            options={matches?.result || []}
            value={keys}
            disabled={noKeys || configure.isLoading || importBusy}
            loading={isLoading && keyword.length >= 2}
            filterOptions={(options) => options}
            isOptionEqualToValue={(a, b) => a.record_id === b.record_id}
            getOptionLabel={(record) =>
              record.title || `Record ${record.record_id}`
            }
            onInputChange={(_, value) => setKeyword(value)}
            onChange={(_, value) => setKeys(value)}
            renderInput={(params) => (
              <TextField {...params} label="Search and select key studies" />
            )}
          />
          <FormControlLabel
            control={
              <Checkbox
                checked={noKeys}
                disabled={
                  configure.isLoading ||
                  importBusy ||
                  importedKeys.length > 0 ||
                  unresolvedImport
                }
                onChange={(event) => {
                  setNoKeys(event.target.checked);
                  setKeys([]);
                }}
              />
            }
            label="No predefined key studies are present in this dataset"
          />
          <Typography variant="body2">
            {allKeys.length} records selected as key studies. Duplicate groups
            count once.
          </Typography>
          {configure.isError && (
            <Alert severity="error">{configure.error?.message}</Alert>
          )}
          <Button
            variant="contained"
            disabled={
              configure.isLoading ||
              importBusy ||
              unresolvedImport ||
              !validParameters ||
              (!noKeys && allKeys.length === 0)
            }
            onClick={() =>
              configure.mutate({
                project_id,
                key_record_ids: allKeys.map((key) => key.record_id),
                no_key_studies: noKeys,
                parameters: Object.fromEntries(
                  Object.entries(parameters).map(([key, value]) => [key, Number(value)]),
                ),
                ...(seedImport && {
                  seed_import: {
                    filename: seedImport.filename,
                    entries: seedImport.rows.map((row) => ({
                      doi: row.doi,
                      title: row.title,
                      authors: row.authors,
                      year: row.year,
                      record_id: row.selected?.record_id ?? null,
                      not_present: row.not_present,
                    })),
                  },
                }),
              })
            }
          >
            Start SAFE screening
          </Button>
          <Typography variant="caption">
            The ELAS l2 phase needs the asreview-dory extension and a model
            download. Independent quality-control screening is a separate step.
          </Typography>
        </Stack>
      </CardContent>
    </Card>
  );
};

export const SafeProgress = ({ status }) => (
  <Stack spacing={1}>
    <Typography variant="subtitle1">{phaseNames[status.phase]}</Typography>
    <Typography variant="body2">
      {status.screened} / {status.total} screening units labeled
    </Typography>
    <Typography variant="body2">
      Random sample: {status.sample_count} / {status.sample_target} minimum;{" "}
      {status.sample_relevant} relevant.
      {status.estimated_relevant != null &&
        ` Estimated relevant total: ${status.estimated_relevant.toFixed(1)}.`}
    </Typography>
    {status.phase === "random" ? (
      <Typography variant="body2">
        AI ranking begins after the minimum sample and both label classes are
        available. No stopping decisions are made from the sample alone.
      </Typography>
    ) : (
      <Box component="ul" sx={{ pl: 2.5, my: 0 }}>
        {status.checks.map((check) => (
          <Typography component="li" variant="body2" key={check.id}>
            {check.met ? "Met" : "Pending"}: {check.label} — {check.value}
            {check.target != null ? ` / ${check.target}` : " / pending sample"}
          </Typography>
        ))}
      </Box>
    )}
  </Stack>
);

const SafeStopping = ({
  project_id,
  status: providedStatus,
  trainingError,
  compact = false,
}) => {
  const client = useQueryClient();
  const [showDetails, setShowDetails] = React.useState(false);
  const { data } = useQuery(
    ["fetchStopping", { project_id }],
    ProjectAPI.fetchStopping,
    { refetchOnWindowFocus: true },
  );
  const status = providedStatus || data;
  const transition = useMutation(ProjectAPI.transitionSafe, {
    onSuccess: () => refreshQueries(client, project_id),
  });
  if (status?.id !== "safe") return null;
  const actionButton = (action, label) => (
    <Button
      variant="contained"
      disabled={transition.isLoading}
      onClick={() => transition.mutate({ project_id, action })}
    >
      {label}
    </Button>
  );
  return (
    <Card variant="outlined" sx={{ my: 2 }} aria-label="SAFE stopping status">
      <CardContent>
        <Stack spacing={2}>
          <Typography variant="h6">
            SAFE {status.paused ? "· Screening paused" : "automatic stopping"}
          </Typography>
          {status.phase !== "random" && (
            <Stack
              direction="row"
              useFlexGap
              flexWrap="wrap"
              spacing={1}
              aria-label="Stopping conditions tracker"
            >
              {status.checks.map((check) => (
                <Chip
                  key={check.id}
                  icon={
                    check.met ? (
                      <CheckCircleOutline />
                    ) : (
                      <RadioButtonUnchecked />
                    )
                  }
                  color={check.met ? "success" : "default"}
                  variant={check.met ? "filled" : "outlined"}
                  label={`${check.met ? "Met" : "Pending"}: ${check.id === "estimate" && status.parameters ? `Screened: ${status.parameters.estimate_multiplier}× estimate` : check.id === "fraction" && status.parameters ? `Screened: ${status.parameters.screened_percent}%` : criterionLabels[check.id]} ${check.value}/${check.target ?? "—"}`}
                />
              ))}
            </Stack>
          )}
          {compact && !showDetails ? (
            <Typography variant="body2">
              {phaseNames[status.phase]} —{" "}
              {status.phase === "random"
                ? `${status.sample_count} / ${status.sample_target} minimum sample`
                : `${status.value} / ${status.params?.n ?? status.checks.find((check) => check.id === "streak")?.target ?? 100} consecutive exclusions; all conditions required`}
            </Typography>
          ) : (
            <SafeProgress status={status} />
          )}
          {compact && (
            <Button size="small" onClick={() => setShowDetails(!showDetails)}>
              {showDetails ? "Hide criteria" : "Show criteria"}
            </Button>
          )}
          {status.exhausted ? (
            <Alert severity="info">
              All screening units have been labeled. This is dataset exhaustion,
              not confirmation that every stopping condition was met. Continue
              with the protocol's independent quality-control review.
            </Alert>
          ) : status.blocked ? (
            <Alert severity="warning">
              A corrected decision invalidated the random sample or the primary
              stopping decision. Check the changed labels before continuing.
            </Alert>
          ) : status.stop ? (
            <Alert severity="success">
              {status.phase === "primary"
                ? "All four primary conditions are met. Continue with ELAS l2 to check the remaining records."
                : "The second-model check is complete. Export the project and perform the independent quality-control review before declaring screening complete."}
            </Alert>
          ) : !status.ready ? (
            <>
              <Alert severity="info">
                Preparing the{" "}
                {status.model === "elas_l2" ? "ELAS l2" : "ELAS u4"} ranking.
                Screening resumes when this model is ready.
              </Alert>
              {!trainingError && (
                <LinearProgress aria-label="Preparing SAFE model" />
              )}
            </>
          ) : null}
          {trainingError && (
            <Alert severity="error">
              {typeof trainingError === "string"
                ? trainingError
                : trainingError.message ||
                  "Model training failed. Check the server log and retry."}
            </Alert>
          )}
          {transition.isError && (
            <Alert severity="error">{transition.error?.message}</Alert>
          )}
          {status.phase === "primary" &&
            status.stop &&
            !status.exhausted &&
            actionButton("secondary", "Start ELAS l2 check")}
          {status.primary_invalidated &&
            !status.exhausted &&
            actionButton(
              "reopen_primary",
              "Return to ELAS u4 with a fresh counter",
            )}
          {(!status.ready || trainingError) &&
            !status.paused &&
            actionButton("retry", "Retry model training")}
        </Stack>
      </CardContent>
    </Card>
  );
};

export default SafeStopping;
