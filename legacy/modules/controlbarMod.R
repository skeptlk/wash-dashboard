controlbarModUI <- function(id) {
  
  ns <- NS(id)
  
  uiOutput(ns("controlbar_uioutput"))
  
}

controlbarMod <- function(input, output, session, credentials = NULL, id_tab) {
  
  ns <- session$ns
  
  output$controlbar_uioutput <- renderUI({
    
    if(id_tab() == "engine_trends"){
      
      controlbarMenu(
        id = "enginetrends_controlbarmenu",
        controlbarItem(
          title = "Fleet configuration",
          enginetrendsfleetconfigurationModUI(
            id = "enginetrends_fleetconfiguration"
          )
        ),
        controlbarItem(
          title = "Preset summary",
          presetsummaryModUI(
            id = "enginetrends_presetsummary"
          )
        )
      )
      
    }
    else if(id_tab() == "fleet_reports"){
      
      controlbarMenu(
        id = "fleetreports_controlbarmenu",
        controlbarItem(
          title = "Preset summary",
          presetsummaryModUI(
            id = "fleetreports_presetsummary"
          )
        )
      )
      
    }
    
    else if(id_tab() == "constructor"){
      
      controlbarMenu(
        id = "constructor_controlbarmenu",
        controlbarItem(
          title = "Parameters",
          constructor_controlbarModUI(
            id = "constructor_parameters"
          )
        )
      )
      
    }
    
    
  })
  
}