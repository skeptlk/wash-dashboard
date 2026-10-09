 presetsummaryModUI <- function(id) {
  
  ns <- NS(id)
  
  uiOutput(ns("ui_presetsummary"))
  
}

presetsummaryMod <- function(input, output, session, credentials, workspace_data, config = NULL, pool, id_tab) {
  
  ns <- session$ns
  
  output$ui_presetsummary <- renderUI({
    
    if(!is.null(workspace_data()$preset)){
      
      df <- workspace_data()$preset
      
      df <- df[with(df, order(id_sort)),]
      
      do.call(
        "accordion",
        c(
          list(
            id = "accordion_presetsummary"
          ),
          lapply(
            1:nrow(df),
            function(i) presetsummaccordionModUI(
              id = paste0(
                i,
                "_presetsummaccordion"
              ),
              preset_i = df[i,]
            )
          )
        )
      ) 
      
    }
    
  })
  
}