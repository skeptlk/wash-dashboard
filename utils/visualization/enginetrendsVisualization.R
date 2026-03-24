enginetrendsVisualization <- function(
  fleetsummary,
  preset,
  params,
  paramssmooth = NULL,
  params_aircraft = NULL,
  alerts = NULL,
  alert_code = NULL,
  maintenance = NULL,
  range_selector = NULL,
  rb_enable_smooth = NULL,
  cgi_show_alerts = NULL,
  smooth_window = NULL,
  rb_graph_size = NULL,
  rb_engine_position = NULL,
  color_engine = NULL,
  ci_baseline = TRUE
){
  
  browser()
  
  list_hc <- list()

  preset <- as.data.frame(preset)
  
  params <- as.data.frame(params)
  
  preset <- preset[preset$table_name != "flightinfo_input",]
  
  preset <- preset[!duplicated(preset),]
  
  params <- params[!is.na(params$engine_id),]
  
  params_aircraft <- as.data.frame(params_aircraft)
  
  params <- params[params$parameter_name %in% preset$main_param_name,]
  
  preset <- preset[with(preset, order(id_sort)),]
  # browser()
  params <- params[with(params, order(flight_datetime)),]
  
  params_aircraft <- params_aircraft[with(params_aircraft, order(flight_datetime)),]

  preset$table_name <- gsub("_", " ", preset$table_name)
  
  preset$table_name <- gsub("RAW ", "", preset$table_name)
  
  if(nrow(preset) > 0){
    
    for(i in 1:nrow(preset)){
      # browser()
      
      if(preset$item_type[i] == "E"){
        
        params <- as.data.frame(params)
        
        params_i <- params[
          params$flight_phase == preset$main_flght_phs[i] &
            params$parameter_name == preset$main_param_name[i],
          ]
        
        alerts_i <- alerts[
          alerts$flight_phase == preset$main_flght_phs[i] &
            alerts$parameter_name == preset$main_param_name[i],
          ]
        
        hc <- highchart(type = "stock")
        
        if(nrow(params_i) > 0){
          
          index_engine_id_color <- 0
          
          for(engine_id in color_engine$engine_id){
            
            index_engine_id_color <- index_engine_id_color + 1
            
            fleetsummary_engine_id <- fleetsummary[fleetsummary$engine_id == engine_id,]
            
            params_engine_id <- params_i[
              params_i$engine_id == engine_id,
              ]
            
            if(nrow(params_engine_id) > 0){
              
              maintenance_engine_id <- maintenance[
                maintenance$engine_id == engine_id,
                ]
              
              alerts_engine_id <- alerts_i[
                alerts_i$aircraft_id %in% fleetsummary_engine_id$aircraft_id &
                  alerts_i$engine_position %in% fleetsummary_engine_id$engine_position,
                ]
              
              flight_phase <- unique(params_engine_id$flight_phase)
              
              parameter_name <- unique(params_engine_id$parameter_name)
              
              ac_reg_new <- unique(params_engine_id$ac_reg_new)
              
              engine_position <- unique(params_engine_id$engine_position)
              
              params_engine_id$float_value[
                !is.na(params_engine_id$integer_value)
                ] <- params_engine_id$integer_value[
                  !is.na(params_engine_id$integer_value)
                  ]
              # browser()
              
              params_engine_id <- params_engine_id[,c("flight_datetime", "float_value")]
              
              # params_engine_id <- rbind(
              #   params_engine_id,
              #   data.frame(
              #     flight_datetime = Sys.time(),
              #     float_value = NA
              #   )
              # )
              
              params_engine_id$float_value <- as.numeric(params_engine_id$float_value)
              
              params_engine_id$float_value <- round(params_engine_id$float_value, 2)
              
              if(length(params_engine_id$float_value) > 1){
                
                params_engine_id$float_value_smooth <- round(
                  caTools::runmean(
                    x = params_engine_id$float_value,
                    k = smooth_window,
                    align = "right" #"center"
                  ),
                  2
                )
                
              }
              else{
                
                params_engine_id$float_value_smooth <- params_engine_id$float_value
                
              }
              
              
              params_engine_id$float_value_smooth <- round(params_engine_id$float_value_smooth, 2)
              
              params_engine_id$float_value_baseline <- mean(
                params_engine_id$float_value_smooth[1:15],na.rm = TRUE
              )
              
              params_engine_id$float_value_baseline <- round(params_engine_id$float_value_baseline, 2)
              
              params_engine_id <- rbind(
                params_engine_id,
                data.frame(
                  flight_datetime = Sys.time(),
                  float_value = NA,
                  float_value_smooth = NA,
                  float_value_baseline = NA
                  #flight_number = NA
                )
              )
              
              params_engine_id <- as.data.table(params_engine_id)
              
              setcolorder(params_engine_id, c("flight_datetime"))
              
              #params_engine_id$flight_number <- as.numeric(params_engine_id$flight_number)
              
              params_engine_id <- as.xts.data.table(params_engine_id)
              
              if(rb_enable_smooth == 1){
                
                hc <- hc %>%
                  hc_add_series(
                    id = paste0(
                      "smooth_",
                      engine_id
                    ),
                    type = "line",
                    params_engine_id$float_value_smooth,
                    color = color_engine$colors_smooth[color_engine$engine_id == engine_id],
                    name = paste(
                      engine_id,
                      ac_reg_new,
                      "(",
                      engine_position,
                      ")",
                      flight_phase,
                      parameter_name,
                      " smooth"
                    )
                    #tooltip = list(pointFormat = "flight number {point.flight_number}")
                  )  %>%
                  hc_xAxis(
                    type = 'datetime',
                    ordinal = FALSE
                  )
              }
              else if(rb_enable_smooth == 2){
                
                hc <- hc %>%
                  hc_add_series(
                    id = paste0(
                      "raw_",
                      engine_id
                    ),
                    params_engine_id$float_value,
                    color = color_engine$colors_raw[color_engine$engine_id == engine_id],
                    name = paste(
                      engine_id,
                      ac_reg_new,
                      "(",
                      engine_position,
                      ")",
                      flight_phase,
                      parameter_name
                    )
                    ,type = "scatter"
                  ) %>%
                  hc_xAxis(
                    type = 'datetime',
                    ordinal = FALSE
                  )
                
              }
              else if(rb_enable_smooth == 3){
                
                hc <- hc %>%
                  hc_add_series(
                    id = paste0(
                      "smooth_",
                      engine_id
                    ),
                    type = "line",
                    params_engine_id$float_value_smooth,
                    color = color_engine$colors_smooth[color_engine$engine_id == engine_id],
                    name = paste(
                      engine_id,
                      ac_reg_new,
                      "(",
                      engine_position,
                      ")",
                      flight_phase,
                      parameter_name,
                      " smooth"
                    )
                  ) %>%
                  hc_add_series(
                    id = paste0(
                      "raw_",
                      engine_id
                    ),
                    params_engine_id$float_value,
                    color = color_engine$colors_raw[color_engine$engine_id == engine_id],
                    name = paste(
                      engine_id,
                      ac_reg_new,
                      "(",
                      engine_position,
                      ")",
                      flight_phase,
                      parameter_name
                    )
                    ,type = "scatter"
                  ) %>%
                  hc_xAxis(
                    type = 'datetime',
                    ordinal = FALSE
                  )
                
              }
              
              if(ci_baseline == TRUE){
                
                hc <- hc %>%
                  hc_add_series(
                    id = paste0(
                      "baseline_",
                      engine_id
                    ),
                    type = "line",
                    dashStyle = "shortdash",
                    params_engine_id$float_value_baseline,
                    color = color_engine$colors_raw[color_engine$engine_id == engine_id],
                    name = paste(
                      engine_id,
                      ac_reg_new,
                      "(",
                      engine_position,
                      ")",
                      flight_phase,
                      parameter_name,
                      " baseline"
                    )
                  ) 
              }
              # browser()
              hc <- hc %>%
                hc_tooltip(
                  headerFormat = "<span style='font-size:10px'>{point.key}</span><table>",
                  pointFormat = "<tr><td style='color:{series.color};padding:0'>{series.name}: </td> <td style='padding:0'><b>{point.y}</b></td></tr>",
                  footerFormat = "</table>",
                  shared = TRUE,
                  useHTML = TRUE
                ) %>% 
                hc_legend(
                  enabled = TRUE
                ) %>%
                hc_rangeSelector(
                  selected = range_selector
                ) %>%
                hc_chart(
                  zoomType = "xy",
                  panning = TRUE,
                  panKey = "shift"
                )
              if("Show alerts" %in% cgi_show_alerts & nrow(alerts_engine_id) > 0){
                
                number_of_alerts <- nrow(alerts_engine_id)
                
                onSeries_prefix <- "raw_"
                
                if (rb_enable_smooth == 1){
                  
                  onSeries_prefix <- "smooth_"
                }
                
                hc <- hc %>%
                  hc_add_series(
                    tibble::tibble(
                      date = as.Date(alerts_engine_id$flight_datetime),
                      title = alerts_engine_id$alert_code,
                      text = alerts_engine_id$alert_code
                    ),
                    hcaes(
                      x = date,
                      text = text
                    ),
                    color = "red",
                    type = "flags", 
                    onSeries = paste0(
                      onSeries_prefix,
                      engine_id
                    ),
                    name = paste(
                      engine_id,
                      ac_reg_new,
                      "(",
                      engine_position,
                      ")",
                      "alerts"
                    )
                  ) %>%
                  hc_xAxis(
                    type = 'datetime',
                    ordinal = FALSE
                  ) %>%
                  hc_chart(
                    zoomType = "xy",
                    panning = TRUE,
                    panKey = "shift"
                  )
              }
              
              if("Show maintenance actions" %in% cgi_show_alerts & nrow(maintenance_engine_id) > 0){
                
                onSeries_prefix <- "raw_"
                
                if (rb_enable_smooth == 1){
                  
                  onSeries_prefix <- "smooth_"
                }
                
                # maintenance <- maintenance_engine_id[!duplicated(maintenance_engine_id),]
                
                maintenance_color_df <- tibble::tibble(
                  date = as.Date(maintenance_engine_id$maint_datetime),
                  title = maintenance_engine_id$ata_code,
                  text = maintenance_engine_id$reason,
                  color = maintenance_engine_id$color
                )
                
                maintenance_color_df$color[is.na(maintenance_color_df$color)] <- "#28a745"
                
                hc <- hc %>%
                  hc_add_series(
                    maintenance_color_df,
                    hcaes(
                      x = date,
                      #text = text,
                      color = color
                    ),
                    # color = "green",
                    type = "flags", 
                    onSeries = paste0(
                      onSeries_prefix,
                      engine_id
                    ),
                    name = paste(
                      engine_id,
                      ac_reg_new,
                      "(",
                      engine_position,
                      ")",
                      "maintenance actions"
                    )
                  ) %>%
                  hc_xAxis(
                    type = 'datetime',
                    ordinal = FALSE
                  )
              }
              
              if("Show previous installations" %in% cgi_show_alerts & nrow(fleetsummary_engine_id[!is.na(fleetsummary_engine_id$removal_datetime),]) > 0){
                
                onSeries_prefix <- "raw_"
                
                if (rb_enable_smooth == 1){
                  
                  onSeries_prefix <- "smooth_"
                }
                
                hc <- hc %>%
                  hc_add_series(
                    tibble::tibble(
                      date = as.Date(
                        fleetsummary_engine_id$removal_datetime[!is.na(fleetsummary_engine_id$removal_datetime)]
                      ),
                      title = "engine removal",
                      text = paste(
                        "engine removal",
                        as.Date(
                          fleetsummary_engine_id$removal_datetime[!is.na(fleetsummary_engine_id$removal_datetime)]
                        )
                      )
                    ),
                    hcaes(
                      x = date,
                      text = text
                    ),
                    color = "orange",
                    type = "flags", 
                    onSeries = paste0(
                      onSeries_prefix,
                      engine_id
                    ),
                    name = paste(
                      engine_id,
                      ac_reg_new,
                      "(",
                      engine_position,
                      ")",
                      "engine removal"
                    )
                  ) %>%
                  hc_xAxis(
                    type = 'datetime',
                    ordinal = FALSE
                  )
              }
              
            }
            
            
            
          }
          
          list_hc[[paste0(
            as.character(i)
          )]] <- hc %>%
            hc_exporting(
              enabled = T,
              filename = paste(
                preset$main_param_name[i],
                preset$main_flght_phs[i],
                "-",
                preset$param_description[i],
                "(",
                preset$table_name[i],
                ")"
              )
            ) %>%
            hc_title(
              text = paste(
                preset$main_param_name[i],
                preset$main_flght_phs[i],
                "-",
                preset$param_description[i],
                "(",
                preset$table_name[i],
                ")"
              ),
              margin = 20,
              align = "left",
              style = list(
                useHTML = TRUE
              )
            ) 
          
        }
        
        else{
          
          hc <- hchart(
            data.frame(
              text = "No data available",
              val = 1,
              color = "#00FFFF"
            ),
            "treemap", 
            hcaes(
              x = text,
              value = val
            ), 
            backgroundColor = "#00FFFF"
          ) %>%
            hc_legend(FALSE) %>%
            hc_title(
              text = paste(
                preset$main_param_name[i],
                preset$main_flght_phs[i],
                "-",
                preset$param_description[i],
                "(",
                preset$table_name[i],
                ")"
              ),
              margin = 20,
              align = "left",
              style = list( useHTML = TRUE)
            )
          
        }
      }
      
      else if(preset$item_type[i] == "A"){
        # browser()
        
        params_i <- params_aircraft[
          params_aircraft$flight_phase == preset$main_flght_phs[i] &
            params_aircraft$parameter_name == preset$main_param_name[i],
          ]
        
        alerts_i <- alerts[
          alerts$flight_phase == preset$main_flght_phs[i] &
            alerts$parameter_name == preset$main_param_name[i],
          ]
        
        hc <- highchart(type = "stock")
        
        if(nrow(params_i) > 0){
          
          colors_smooth <- c("#007bff", "#17a2b8", "#28a745", "#ffc107", "#dc3545", "#f012be")
          
          colors_raw <- paste0(
            colors_smooth,
            "70"
          )
          
          colors_smooth <- rep(color_engine$colors_smooth, length.out = length(unique(fleetsummary$aircraft_id)))
          
          colors_raw <- rep(color_engine$colors_raw, length.out = length(unique(fleetsummary$aircraft_id)))
          
          vec_aircraft_id <- stringr::str_sort(unique(fleetsummary$aircraft_id), decreasing = FALSE, numeric = TRUE)
          
          color_aircraft <- data.frame(
            colors_raw = colors_raw,
            colors_smooth = colors_smooth,
            aircraft_id = vec_aircraft_id,
            stringsAsFactors = FALSE
          )
          
          for(aircraft_id in color_aircraft$aircraft_id){
            
            fleetsummary_aircraft_id <- fleetsummary[fleetsummary$aircraft_id == unique(aircraft_id),]
            
            params_aircraft_id <- params_i[
              params_i$aircraft_id %in% fleetsummary_aircraft_id$aircraft_id,
              ]
            
            alerts_aircraft_id <- alerts_i[
              alerts_i$aircraft_id %in% fleetsummary_aircraft_id$aircraft_id,
              ]
            
            flight_phase <- unique(params_aircraft_id$flight_phase)
            
            parameter_name <- unique(params_aircraft_id$parameter_name)
            
            params_aircraft_id$float_value[
              !is.na(params_aircraft_id$integer_value)
              ] <- params_aircraft_id$integer_value[
                !is.na(params_aircraft_id$integer_value)
                ]
            
            params_aircraft_id <- params_aircraft_id[,c("flight_datetime", "float_value")]
            
            # params_aircraft_id <- rbind(
            #   params_aircraft_id,
            #   data.frame(
            #     flight_datetime = Sys.time(),
            #     float_value = NA
            #   )
            # )
            
            params_aircraft_id$float_value <- as.numeric(params_aircraft_id$float_value)
            
            params_aircraft_id$float_value <- round(params_aircraft_id$float_value, 2)
            
            params_aircraft_id$float_value_smooth <- round(
              caTools::runmean(
                x = params_aircraft_id$float_value,
                k = smooth_window,
                align = "right" #"center"
              ),
              2
            )
            
            params_aircraft_id <- rbind(
              params_aircraft_id,
              data.frame(
                flight_datetime = Sys.time(),
                float_value = NA,
                float_value_smooth = NA
              )
            )
            
            params_aircraft_id <- as.data.table(params_aircraft_id)
            
            setcolorder(params_aircraft_id, c("flight_datetime"))
            
            params_aircraft_id <- as.xts.data.table(params_aircraft_id)
            
            if(rb_enable_smooth == 1){
              
              hc <- hc %>%
                hc_add_series(
                  id = paste0(
                    "smooth_",
                    fleetsummary_aircraft_id$aircraft_id
                  ),
                  type = "line",
                  params_aircraft_id$float_value_smooth,
                  color = color_aircraft$colors_smooth[color_aircraft$aircraft_id == aircraft_id],
                  name = paste(
                    unique(aircraft_id),
                    unique(fleetsummary_aircraft_id$ac_reg_new),
                    unique(flight_phase),
                    unique(parameter_name),
                    " smooth"
                  )
                ) %>%
                hc_xAxis(
                  type = 'datetime',
                  ordinal = FALSE
                )
            }
            else if(rb_enable_smooth == 2){
              
              hc <- hc %>%
                hc_add_series(
                  id = paste0(
                    "raw_",
                    fleetsummary_aircraft_id$engine_position
                  ),
                  params_aircraft_id$float_value,
                  color = color_aircraft$colors_raw[color_aircraft$aircraft_id == aircraft_id],
                  name = paste(
                    unique(aircraft_id),
                    unique(fleetsummary_aircraft_id$ac_reg_new),
                    unique(flight_phase),
                    unique(parameter_name)
                  )
                  ,type = "scatter"
                ) %>%
                hc_xAxis(
                  type = 'datetime',
                  ordinal = FALSE
                )
              
            }
            else if (rb_enable_smooth == 3){
              
              hc <- hc %>%
                hc_add_series(
                  id = paste0(
                    "smooth_",
                    fleetsummary_aircraft_id$aircraft_id
                  ),
                  type = "line",
                  params_aircraft_id$float_value_smooth,
                  color = color_aircraft$colors_smooth[color_aircraft$aircraft_id == aircraft_id],
                  name = paste(
                    unique(aircraft_id),
                    unique(fleetsummary_aircraft_id$ac_reg_new),
                    unique(flight_phase),
                    unique(parameter_name),
                    " smooth"
                  )
                ) %>%
                hc_add_series(
                  id = paste0(
                    "raw_",
                    fleetsummary_aircraft_id$engine_position
                  ),
                  params_aircraft_id$float_value,
                  color = color_aircraft$colors_raw[color_aircraft$aircraft_id == aircraft_id],
                  name = paste(
                    unique(aircraft_id),
                    unique(fleetsummary_aircraft_id$ac_reg_new),
                    unique(flight_phase),
                    unique(parameter_name)
                  )
                  ,type = "scatter"
                ) %>%
                hc_xAxis(
                  type = 'datetime',
                  ordinal = FALSE
                )
              
            }
            
            hc <- hc %>%
              hc_tooltip(
                headerFormat = "<span style='font-size:10px'>{point.key}</span><table>",
                pointFormat = "<tr><td style='color:{series.color};padding:0'>{series.name}: </td> <td style='padding:0'><b>{point.y}</b></td></tr>",
                footerFormat = "</table>",
                shared = TRUE,
                useHTML = TRUE
              ) %>% 
              hc_legend(
                enabled = TRUE
              ) %>%
              hc_rangeSelector(
                selected = range_selector
              ) %>%
              hc_chart(
                zoomType = "xy"
              )
            
            if("Show alerts" %in% cgi_show_alerts & nrow(alerts_aircraft_id) > 0){
              
              number_of_alerts <- nrow(alerts_aircraft_id)
              
              onSeries_prefix <- "raw_"
              
              if (rb_enable_smooth == 1){
                
                onSeries_prefix <- "smooth_"
              }
              
              hc <- hc %>%
                hc_add_series(
                  tibble::tibble(
                    date = as.Date(alerts_aircraft_id$flight_datetime),
                    title = alerts_aircraft_id$alert_code,
                    text = alerts_aircraft_id$alert_code
                    #text = unique(alert_code$short_description[alert_code$alert_code == unique(alerts_aircraft_id$alert_code)])
                  ),
                  hcaes(
                    x = date,
                    text = text
                  ),
                  color = "red",
                  type = "flags", 
                  onSeries = paste0(
                    onSeries_prefix,
                    unique(fleetsummary_alerts_aircraft_id$aircraft_id)
                  ),
                  name = paste(
                    unique(fleetsummary_alerts_aircraft_id$aircraft_id),
                    "alerts"
                  )
                ) %>%
                hc_xAxis(
                  type = 'datetime',
                  ordinal = FALSE
                ) 
            }
            
            if("Show maintenance actions" %in% cgi_show_alerts & nrow(maintenance) > 0){
              
              onSeries_prefix <- "raw_"
              
              if (rb_enable_smooth == 1){
                
                onSeries_prefix <- "smooth_"
              }
              
              maintenance <- maintenance[!duplicated(maintenance),]
              
              maintenance$color[is.na(maintenance$color)] <- "#28a745"
              
              hc <- hc %>%
                hc_add_series(
                  tibble::tibble(
                    date = as.Date(maintenance$maint_datetime),
                    title = maintenance$ata_code,
                    text = maintenance$reason,
                    color = maintenance$color
                  ),
                  hcaes(
                    x = date,
                    text = text,
                    color = color
                  ),
                  #color = "green",
                  type = "flags", 
                  onSeries = paste0(
                    onSeries_prefix,
                    unique(fleetsummary_aircraft_id$aircraft_id)
                  ),
                  name = paste(
                    unique(fleetsummary_aircraft_id$aircraft_id),
                    "maintenance actions"
                  )
                ) %>%
                hc_xAxis(
                  type = 'datetime',
                  ordinal = FALSE
                ) 
            }
            
          }
          
          
          
        }
        
        else{
          
          hc <- hchart(
            data.frame(
              text = "No data available",
              val = 1,
              color = "#00FFFF"
            ),
            "treemap", 
            hcaes(
              x = text,
              value = val
            ), 
            backgroundColor = "#00FFFF"
          ) %>%
            hc_legend(FALSE) %>%
            hc_title(
              text = paste(
                preset$main_param_name[i],
                preset$main_flght_phs[i],
                "-",
                preset$param_description[i],
                "(",
                preset$table_name[i],
                ")"
              ),
              margin = 20,
              align = "left",
              style = list( useHTML = TRUE)
            )
          
        }
      }
      
      list_hc[[paste0(
        as.character(i)
      )]] <- hc %>%
        hc_exporting(
          enabled = T,
          filename = paste(
            preset$main_param_name[i],
            preset$main_flght_phs[i],
            "-",
            preset$param_description[i],
            "(",
            preset$table_name[i],
            ")"
          )
        ) %>%
        hc_title(
          text = paste(
            preset$main_param_name[i],
            preset$main_flght_phs[i],
            "-",
            preset$param_description[i],
            "(",
            preset$table_name[i],
            ")"
          ),
          margin = 20,
          align = "left",
          style = list(
            useHTML = TRUE
          )
        ) 
      # browser()
      print(i)
    }
    # browser()
  }
  
  if(rb_graph_size == "multiple"){
    
    return(
      hw_grid(
        list_hc,
        rowheight = 500,
        ncol = 2
      )
    )
    
  }
  else if(rb_graph_size == "line"){
    
    return(
      hw_grid(
        list_hc,
        rowheight = 500,
        ncol = 1
      )
    )
    
  }
  else if(rb_graph_size == "one"){
    return(
      hw_grid(
        list_hc,
        rowheight = 740,
        ncol = 1
      )
    )
    
  }
  
}