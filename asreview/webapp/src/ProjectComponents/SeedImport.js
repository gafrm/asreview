import React from "react";
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Checkbox,
  Chip,
  FormControlLabel,
  LinearProgress,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation, useQuery } from "react-query";
import { ProjectAPI } from "api";

const recordLabel = (record) =>
  [
    record.title || `Record ${record.record_id}`,
    record.authors && String(record.authors).slice(0, 160),
    record.year,
    record.doi,
  ]
    .filter(Boolean)
    .join(" · ");

const SeedRow = ({ project_id, row, onChange, disabled }) => {
  const [keyword, setKeyword] = React.useState("");
  const { data, isLoading, isError } = useQuery(
    ["fetchPriorSearch", { project_id, keyword }],
    ProjectAPI.fetchPriorSearch,
    {
      enabled: keyword.length >= 2 && !row.not_present,
      refetchOnWindowFocus: false,
    },
  );
  const options = Array.from(
    new Map(
      [row.selected, ...(data?.result || []), ...row.candidates]
        .filter(Boolean)
        .map((record) => [record.record_id, record]),
    ).values(),
  );
  const resolved = row.selected || row.not_present;
  return (
    <Box
      component="section"
      aria-label={`Seed entry ${row.id + 1}`}
      sx={{ p: 2, border: 1, borderColor: "divider", borderRadius: 1 }}
    >
      <Stack spacing={1}>
        <Typography variant="subtitle2">
          {row.id + 1}. {row.title || row.doi}
        </Typography>
        <Typography variant="caption">
          {[row.authors, row.year, row.title && row.doi]
            .filter(Boolean)
            .join(" · ")}
        </Typography>
        <Box>
          <Chip
            size="small"
            color={resolved ? "default" : "warning"}
            label={
              row.not_present
                ? "Confirmed absent"
                : row.selected
                  ? "Selected"
                  : "Needs review"
            }
          />
        </Box>
        <Typography variant="body2">{row.reason}</Typography>
        {row.candidate_count > row.candidates.length && (
          <Typography variant="caption">
            Showing the first {row.candidates.length} of {row.candidate_count}{" "}
            matches. Search to find another record.
          </Typography>
        )}
        <Autocomplete
          options={options}
          value={row.selected || null}
          disabled={disabled || row.not_present}
          loading={isLoading && keyword.length >= 2}
          filterOptions={(items) => items}
          isOptionEqualToValue={(a, b) => a.record_id === b.record_id}
          getOptionLabel={recordLabel}
          onInputChange={(_, value, reason) => {
            if (reason === "input" || reason === "clear") setKeyword(value);
          }}
          onChange={(_, selected) =>
            onChange({ ...row, selected, not_present: false })
          }
          renderInput={(params) => (
            <TextField
              {...params}
              label={`Match for seed ${row.id + 1}`}
              helperText="Choose a suggested record or search by title or author."
            />
          )}
        />
        {isError && (
          <Alert severity="error">
            Search failed. Try entering the title again.
          </Alert>
        )}
        <FormControlLabel
          control={
            <Checkbox
              checked={row.not_present}
              disabled={disabled}
              onChange={(event) =>
                onChange({
                  ...row,
                  not_present: event.target.checked,
                  selected: null,
                })
              }
            />
          }
          label="I confirm this study is not present in this dataset"
        />
      </Stack>
    </Box>
  );
};

export default function SeedImport({
  project_id,
  value,
  onChange,
  onBusy,
  disabled,
}) {
  const [showMatches, setShowMatches] = React.useState(false);
  const upload = useMutation(ProjectAPI.previewSeedImport, {
    onSuccess: (report) => {
      onChange({
        ...report,
        rows: report.rows.map((row) => ({
          ...row,
          selected: row.match,
          not_present: false,
        })),
      });
      onBusy(false);
      setShowMatches(false);
    },
  });
  const unresolved =
    value?.rows.filter((row) => !row.selected && !row.not_present).length || 0;
  const autoMatched =
    value?.rows.filter((row) => row.status === "matched").length || 0;
  const clear = () => {
    upload.reset();
    onChange(null);
    onBusy(false);
  };
  return (
    <Stack spacing={2}>
      <Typography variant="body2">
        Upload your seed list as CSV or RIS. CSV columns: doi and/or title;
        authors and year are optional. Up to 1,000 articles, 2 MB.
      </Typography>
      <Box>
        <Button
          component="label"
          variant="outlined"
          disabled={disabled || upload.isLoading}
        >
          Import seed list (CSV/RIS)
          <input
            type="file"
            aria-label="Import seed list"
            accept=".csv,.ris"
            hidden
            disabled={disabled || upload.isLoading}
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (file) {
                onChange(null);
                onBusy(true);
                upload.mutate({ project_id, file });
              }
            }}
          />
        </Button>
        {(value || upload.isError) && (
          <Button onClick={clear} disabled={disabled || upload.isLoading}>
            Clear import
          </Button>
        )}
      </Box>
      {upload.isLoading && (
        <LinearProgress aria-label="Matching seed articles" />
      )}
      {upload.isError && (
        <Alert severity="error">{upload.error?.message}</Alert>
      )}
      {value && (
        <>
          <Alert severity={unresolved ? "warning" : "success"}>
            {value.filename}: {value.rows.length} entries; {autoMatched}{" "}
            automatically matched; {unresolved} still need review. Resolve every
            entry before starting SAFE. Studies confirmed absent are recorded
            but do not count toward the stopping condition.
          </Alert>
          {autoMatched > 0 && (
            <Button onClick={() => setShowMatches(!showMatches)}>
              {showMatches ? "Hide matched studies" : "Review matched studies"}
            </Button>
          )}
          {value.rows
            .filter(
              (row) =>
                row.status !== "matched" ||
                showMatches ||
                (!row.selected && !row.not_present),
            )
            .map((row) => (
              <SeedRow
                key={row.id}
                project_id={project_id}
                row={row}
                disabled={disabled || upload.isLoading}
                onChange={(updated) =>
                  onChange({
                    ...value,
                    rows: value.rows.map((item) =>
                      item.id === updated.id ? updated : item,
                    ),
                  })
                }
              />
            ))}
        </>
      )}
    </Stack>
  );
}
