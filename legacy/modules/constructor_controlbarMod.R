constructor_controlbarModUI <- function(id) {
  
  ns <- NS(id)
  
  uiOutput(ns("ui_constructor_id_sorted"))
  
}

constructor_controlbarMod <- function(input, output, session, credentials, headerselectors, pool, id_tab) {
  
  ns <- session$ns
  
  output$ui_constructor_id_sorted <- renderUI({
      
    if(id_tab() == "constructor"){
      browser()
      
      labels_vec <- c(
        paste0(
          headerselectors$constructor$constructor_parameters_takeoff_pi(),
          " (TAKEOFF)"
        ),
        paste0(
          headerselectors$constructor$constructor_parameters_cruise_pi(),
          " (CRUISE)"
        ),
        paste0(
          headerselectors$constructor$constructor_parameters_climb_pi(),
          " (CLIMB)"
        )
      )
      
      labels_vec <- labels_vec[!(labels_vec %in% c(" (TAKEOFF)"," (CRUISE)"," (CLIMB)"))]
      
      labels <- as.list(
        labels_vec
      )
      
      
      # browser()
      rank_list_basic <- rank_list(
        text = "Drag the items in any desired order",
        labels = labels,
        input_id = ns("rank_list_basic")
      )
      
      rank_list_basic
      
    }
    
  })
  
  constructor_id_sorted <- list(
    rank_list_basic = reactive({input$rank_list_basic})
  )
  
  return(constructor_id_sorted)
  
}