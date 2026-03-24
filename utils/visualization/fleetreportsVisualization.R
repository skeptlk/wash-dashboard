fleetreportsVisualization <- function(
  fleetsummary,
  preset,
  params,
  paramssmooth = NULL,
  params_aircraft = NULL,
  color_engine = NULL
){
  
  list_hc <- list()
  # browser()
  preset <- as.data.frame(preset)
  
  params <- as.data.frame(params)
  
  params_aircraft <- as.data.frame(params_aircraft)
  
  preset <- preset[with(preset, order(id_sort)),]
  
  params_gr <- data.frame(
    params %>%
      group_by(
        ac_reg_new,
        aircraft_type,
        engine_id,
        engine_position,
        flight_phase,
        parameter_name
        # flight_datetime,
        #float_value
      ) %>%
      summarise(
        start_date = min(as.Date(flight_datetime)),
        end_date = max(as.Date(flight_datetime)),
        min_float_value = min(float_value,na.rm = T),
        mean_float_value = round(mean(float_value,na.rm = T),2),
        max_float_value = max(float_value,na.rm = T)
      )
  )
  
  params_gr$ac_reg_pos <- paste0(
    params_gr$ac_reg_new,
    " (",
    params_gr$engine_position,
    ")"
  )
  # browser()
  params_aircraft_gr <- data.frame(
    params_aircraft %>%
      group_by(
        ac_reg_new,
        aircraft_type,
        flight_phase,
        parameter_name
        # flight_datetime,
        #float_value
      ) %>%
      summarise(
        start_date = min(as.Date(flight_datetime)),
        end_date = max(as.Date(flight_datetime)),
        min_float_value = min(float_value,na.rm = T),
        mean_float_value = round(mean(float_value,na.rm = T),2),
        max_float_value = max(float_value,na.rm = T)
      )
  )
  
  for(i in 1:nrow(preset)){
    
    if(preset$item_type[i] == "E"){
      
      params_i <- params_gr[
        params_gr$flight_phase == preset$main_flght_phs[i] &
          params_gr$parameter_name == preset$main_param_name[i],
        ]
      
      hc <- highchart(type = "stock")
      
      params_i <- params_i[with(params_i, order(-mean_float_value)),]
      
      list_hc[[as.character(i)]] <- hchart(
        params_i,
        "bar",
        hcaes(
          x = engine_id,
          y = mean_float_value
        ),
        dataLabels = list(enabled = TRUE, format='{point.ac_reg_pos}')
      ) %>% 
        hc_title(
          text = paste(
            preset$main_flght_phs[i],
            preset$main_param_name[i],
            preset$param_description[i],
            " (",
            preset$table_name[i],
            " )"
          ),
          margin = 20,
          align = "left",
          style = list( useHTML = TRUE) #color = "#22A884",
        )
      
    }
    
    else if(preset$item_type[i] == "A"){
      
      params_i <- params_aircraft_gr[
        params_aircraft_gr$flight_phase == preset$main_flght_phs[i] &
          params_aircraft_gr$parameter_name == preset$main_param_name[i],
        ]
      
      hc <- highchart(type = "stock")
      
      params_i <- params_i[with(params_i, order(-mean_float_value)),]
      
      list_hc[[as.character(i)]] <- hchart(
        params_i,
        "bar",
        hcaes(
          x = ac_reg_new,
          y = mean_float_value
        ),
        dataLabels = list(enabled = TRUE, format='{point.ac_reg_new}')
      ) %>% 
        hc_title(
          text = paste(
            preset$main_flght_phs[i],
            preset$main_param_name[i],
            preset$param_description[i],
            " (",
            preset$table_name[i],
            " )"
          ),
          margin = 20,
          align = "left",
          style = list( useHTML = TRUE) #color = "#22A884",
        )
      
    }
    
  }
  
  hw_grid(
    list_hc,
    rowheight = 500,
    ncol = 2
  )
  
}