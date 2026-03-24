fleetconfaccordionModUI <- function(id, fleetsummary, color_engine, params_input_flight_datetime, params_output_flight_datetime) {
  
  ns <- NS(id)
  
  accordionItem(
    title = paste0(
      paste0(
        unique(fleetsummary$engine_id),
        " ",
        unique(fleetsummary$ac_reg_new),
        " (pos. ",
        unique(fleetsummary$engine_position),
        ") "
      )

    ),
    status = color_engine$status,
    "operator:",
    h5(unique(fleetsummary$operator)),
    hr(),
    "aircraft type:",
    h5(unique(fleetsummary$aircraft_grp)),
    hr(),
    "engine type:",
    h5(unique(fleetsummary$engine_type)),
    hr(),
    "install datetime:",
    h5(max(fleetsummary$install_datetime[!is.na(fleetsummary$install_datetime)],na.rm = TRUE)),
    hr(),
    "removal datetime:",
    h5(max(fleetsummary$removal_datetime[!is.na(fleetsummary$removal_datetime)],na.rm = TRUE)),
    hr(),
    "last datetime input point:",
    h5(params_input_flight_datetime),
    hr(),
    "last datetime output point:",
    h5(params_output_flight_datetime),
    hr(),
    "n1 modifier:",
    h5(unique(fleetsummary$n1_modifier))
  )
}