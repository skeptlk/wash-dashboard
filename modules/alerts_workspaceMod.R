alerts_workspaceModUI <- function(id) {
  
  ns <- NS(id)
  
  uiOutput(ns("alerts_workspace"))
  
}

alerts_workspaceMod <- function(input, output, session, credentials, headerselectors, pool, id_tab) {
  
  ns <- session$ns
  
  alerts_data <- reactiveValues(
    fleetsummary = NULL,
    preset = NULL,
    params = NULL,
    params_aircraft = NULL,
    alerts = NULL,
    alert_code = NULL,
    alerts = NULL,
    config = NULL
  )
  
  
  observeEvent(headerselectors$alerts$update_alerts_data(), {
    
    alerts_data$fleetsummary <- pool %>%
      tbl(in_schema("ecmapp", "fleetsummary")) %>%
      filter(
        ac_reg_new %in% !!headerselectors$alerts$alerts_acreg_pi()
      ) %>%
      collect()
    
    alerts_data$alerts <- pool %>%
      tbl(in_schema("ecmapp", "alert_output")) %>%
      filter(
        aircraft_id %in% !!unique(alerts_data$fleetsummary$aircraft_id)
      ) %>%
      collect()
    
  })
  
  output$alerts_table <- renderReactable({
    
    req(alerts_data$alerts)
    
    if (is.null(alerts_data$alerts)){
      return()
    }
    else{

      reactable(
        alerts_data$alerts,
        searchable = TRUE,
        filterable = TRUE,
        showPageInfo = TRUE,
        showPagination = TRUE,
        
        wrap = FALSE,
        resizable = TRUE,
        striped = TRUE, 
        highlight = TRUE,
        groupBy = c(
          "aircraft_id"
          # "engine_position",
          # "engine_id"
        ),
        bordered = TRUE
      )
    }
    
  })
  
  output$alerts_workspace <- renderUI({
    
    if(id_tab() == "alerts"){
      
      fluidRow(
        bs4TabCard(
          width = 12,
          maximizable = TRUE,
          solidHeader = FALSE,
          sidebar = boxSidebar(),
          tabPanel(
            title = "Alerts table",
            withSpinner(reactableOutput(ns("alerts_table")))
          )
        )  
      )
      
    }
    
  })
  
}