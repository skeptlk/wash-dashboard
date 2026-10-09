enginetrendsfleetconfigurationModUI <- function(id) {
  
  ns <- NS(id)
  
  uiOutput(ns("ui_enginetrendsfleetconfiguration"))
  
}

enginetrendsfleetconfigurationMod <- function(input, output, session, credentials, enginetrends_data, config = NULL,pool, id_tab) {
  
  ns <- session$ns
  
  output$ui_enginetrendsfleetconfiguration <- renderUI({
      
    if(id_tab() == "engine_trends"){
      
      if(!is.null(enginetrends_data()$fleetsummary)){
        
        df <- enginetrends_data()$fleetsummary
        
        df <- df[with(df, order(aircraft_id, engine_position)),]
        
        df$install_date <- as.Date(df$install_datetime)
        
        df <- df[!duplicated(df[,c("aircraft_id","engine_id","install_date","removal_datetime")]),]
        
        browser()
        
        if(nrow(df) > 0){
          
          do.call(
            "accordion",
            c(
              list(id = "accordion_fleetconfiguration"),
              lapply(
                1:nrow(df),
                function(i) fleetconfaccordionModUI(
                  id = paste0(
                    df$engine_id[i],
                    "_fleetconfigurationaccordion"
                  ),
                  fleetsummary = df[i,],
                  color_engine = enginetrends_data()$color_engine[
                    enginetrends_data()$color_engine$engine_id == df$engine_id[i],
                    ],
                  params_input_flight_datetime = max(
                    enginetrends_data()$params$flight_datetime[
                      enginetrends_data()$params$engine_id == df$engine_id[i]
                      ],
                    na.rm = TRUE
                  ),
                  params_output_flight_datetime = max(
                    enginetrends_data()$params$flight_datetime[
                      enginetrends_data()$params$engine_id == df$engine_id[i]
                      ],
                    na.rm = TRUE
                  )
                )
              )
            )
          )
          # do.call(
          #   "accordion",
          #   c(
          #     list(id = "accordion_fleetconfiguration"),
          #     lapply(
          #       unique(df$aircraft_id),
          #       function(aircraft_id) {
          #         
          #         df_aircraft_id <- df[df$aircraft_id == aircraft_id,]
          #         do.call(
          #           c,
          #           c(
          #             accordionItem(
          #               title = paste0(
          #                 unique(df_aircraft_id$ac_reg_new),
          #                 " (",
          #                 unique(df_aircraft_id$aircraft_type),
          #                 ")"
          #               ),
          #               #status = "white",
          #               "operator:",
          #               h5(unique(df_aircraft_id$operator)),
          #               "A/C reg old:",
          #               h5(unique(df_aircraft_id$ac_reg_old)),
          #               "aircraft_id:",
          #               h5(unique(df_aircraft_id$aircraft_id))
          #             ),
          #             lapply(
          #               1:nrow(df_aircraft_id),
          #               function(i){
          #                 fleetconfaccordionModUI(
          #                   id = paste0(
          #                     df_aircraft_id$engine_id[i],
          #                     "_fleetconfigurationaccordion"
          #                   ),
          #                   fleetsummary = df_aircraft_id[i,],
          #                   color_engine = enginetrends_data()$color_engine[
          #                     enginetrends_data()$color_engine$engine_id == df_aircraft_id$engine_id[i],
          #                     ],
          #                   params_input_flight_datetime = max(
          #                     enginetrends_data()$params$flight_datetime[
          #                       enginetrends_data()$params$engine_id == df_aircraft_id$engine_id[i]
          #                       ],
          #                     na.rm = TRUE
          #                   ),
          #                   params_output_flight_datetime = max(
          #                     enginetrends_data()$params$flight_datetime[
          #                       enginetrends_data()$params$engine_id == df_aircraft_id$engine_id[i]
          #                       ],
          #                     na.rm = TRUE
          #                   )
          #                 )
          #               }
          #             )
          #           ) 
          #         )
          #       }
          #     )
          #   )
          # )
          
        }
        else{
          
          h3("All engines removed")
          
        }

        
      }
      
    }
    
  })
  
}