### Changed
- The shipped default `LANE_TOOL_CAP` is now 150 (was 250). In one measured 13-day session the p90 lane was 97 tool calls, and 30 of 682 lanes went past 150 calls and held 13.5% of lane input tokens; the checkpoint fires at 80% (120 calls). An existing `LANE_TOOL_CAP` value is still kept on merge.
