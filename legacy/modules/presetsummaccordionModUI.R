presetsummaccordionModUI <- function(id, preset_i) {
  
  ns <- NS(id)
  
  accordionItem(
    title = paste0(
      paste(
        unique(preset_i$main_param_name),
        unique(preset_i$main_flght_phs)
      )

    ),
    status = "warning",
    "parameter name:",
    h5(unique(preset_i$main_param_name)),
    hr(),
    "flight phase:",
    h5(unique(preset_i$main_flght_phs)),
    hr(),
    "source table:",
    h5(unique(preset_i$table_name)),
    hr(),
    "parameter description:",
    h5(unique(preset_i$param_description)),
    hr(),
    "item type:",
    h5(unique(preset_i$item_type))
  )
}