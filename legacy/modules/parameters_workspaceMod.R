parameters_workspaceModUI <- function(id) {
  
  ns <- NS(id)
  
  uiOutput(ns("parameters_workspace"))
  
}

parameters_workspaceMod <- function(input, output, session, credentials, pool, id_tab) {
  
  ns <- session$ns
  
  output$parameters_table <- renderReactable({
    
    parameters_table <- pool %>% 
      tbl(in_schema("ecmapp", "parameters")) %>%
      # filter(
      #   aircraft_type == "ATR72-212"
      # ) %>%
      collect()
    
    parameters_table$table_name <- gsub(
      "_",
      " ",
      parameters_table$table_name
    )
    
    parameters_table$table_name <- gsub(
      "RAW ",
      "",
      parameters_table$table_name
    )
    
    reactable(
      parameters_table,
      searchable = TRUE,
      filterable = TRUE,
      showPageInfo = TRUE,
      showPagination = TRUE,
      
      wrap = FALSE,
      resizable = TRUE,
      striped = TRUE, 
      highlight = TRUE,
      groupBy = c(
        "aircraft_type",
        "table_name",
        "flight_phase"
      ),
      bordered = TRUE
    )
    
  })
  
  output$parameters_workspace <- renderUI({
    
    fluidRow(
      bs4TabCard(
        width = 12,
        maximizable = TRUE,
        solidHeader = FALSE,
        sidebar = boxSidebar(),
        tabPanel(
          title = "Parameters table",
          # withSpinner(reactableOutput(ns("parameters_table")))
          
          div(
            style = 'overflow-y:scroll;height:900px;',
            withSpinner(reactableOutput(ns("parameters_table")))
          )
        )
      )  
    )
    
  })
  
}